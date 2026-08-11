"""
Tests for the GitHub API interaction layer in update_pr_comment.py.

All HTTP calls are mocked with unittest.mock — no network access required.
Covers: github_api, find_ovos_comments, merge_sections,
        deduplicate_comments, and the main() flow.
"""
from __future__ import annotations

import email.message
import json
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from update_pr_comment import (  # noqa: E402
    COMMENT_MARKER,
    RETRY_ATTEMPTS,
    RETRY_MAX_WAIT,
    build_section,
    deduplicate_comments,
    find_ovos_comments,
    github_api,
    insert_or_replace_section,
    main,
    merge_sections,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _urlopen_mock(response_data, status=200):
    """Return a mock that behaves like urllib.request.urlopen(req)."""
    raw = json.dumps(response_data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=mock_resp)


def _http_error(code: int, body: str = "error", headers: dict | None = None):
    """Build a urllib.error.HTTPError suitable for raising in tests."""
    return urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg="HTTP Error",
        hdrs=email.message.Message() if headers is None else _headers(headers),
        fp=BytesIO(body.encode()),
    )


def _headers(values: dict) -> email.message.Message:
    msg = email.message.Message()
    for k, v in values.items():
        msg[k] = str(v)
    return msg


FAKE_TOKEN = "ghp_testtoken"

OVOS_COMMENT = {
    "id": 111,
    "body": f"{COMMENT_MARKER}\n## Hello!\n\nI've aggregated the results.\n\n"
            "<!-- section:coverage -->\n### 📊 Coverage\n\nGreat work!\n\n75%\n"
            "<!-- /section:coverage -->\n\n---\n_Signed._",
}

OTHER_COMMENT = {
    "id": 222,
    "body": "Just a normal review comment, no marker here.",
}


# ---------------------------------------------------------------------------
# github_api
# ---------------------------------------------------------------------------

class TestGithubApi:
    def test_raises_when_token_missing(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(EnvironmentError, match="GITHUB_TOKEN"):
            github_api("GET", "/repos/foo/bar/issues/1/comments")

    def test_get_request_uses_correct_url_and_headers(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        mock_open = _urlopen_mock([{"id": 1}])
        with patch("urllib.request.urlopen", mock_open):
            result = github_api("GET", "/repos/foo/bar/issues/1/comments")
        assert result == [{"id": 1}]
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://api.github.com/repos/foo/bar/issues/1/comments"
        assert req.get_header("Authorization") == f"Bearer {FAKE_TOKEN}"
        assert req.get_header("Accept") == "application/vnd.github+json"
        assert req.method == "GET"

    def test_post_request_sends_json_body(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        mock_open = _urlopen_mock({"id": 42, "body": "created"})
        with patch("urllib.request.urlopen", mock_open):
            result = github_api("POST", "/repos/foo/bar/issues/1/comments", data={"body": "hi"})
        assert result["id"] == 42
        req = mock_open.call_args[0][0]
        assert req.method == "POST"
        assert json.loads(req.data) == {"body": "hi"}

    def test_patch_request(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        mock_open = _urlopen_mock({"id": 99, "body": "updated"})
        with patch("urllib.request.urlopen", mock_open):
            result = github_api("PATCH", "/repos/foo/bar/issues/comments/99", data={"body": "new"})
        assert result["id"] == 99
        req = mock_open.call_args[0][0]
        assert req.method == "PATCH"

    def test_delete_request(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        mock_open = _urlopen_mock({})
        with patch("urllib.request.urlopen", mock_open):
            github_api("DELETE", "/repos/foo/bar/issues/comments/99")
        req = mock_open.call_args[0][0]
        assert req.method == "DELETE"

    def test_http_error_is_reraised(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        err = _http_error(404, '{"message":"Not Found"}')
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                github_api("GET", "/repos/foo/bar/issues/999/comments")
        assert exc_info.value.code == 404

    def test_returns_list_response(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        payload = [{"id": 1}, {"id": 2}]
        with patch("urllib.request.urlopen", _urlopen_mock(payload)):
            result = github_api("GET", "/repos/foo/bar")
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# find_ovos_comments
# ---------------------------------------------------------------------------

class TestGithubApiRetries:
    """Transient GitHub failures must not red-out a check whose real work passed."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self):
        with patch("update_pr_comment.time.sleep") as sleep:
            self.sleep = sleep
            yield

    def test_retries_5xx_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        ok = _urlopen_mock([{"id": 1}])
        with patch("urllib.request.urlopen", side_effect=[_http_error(503), ok.return_value]):
            assert github_api("GET", "/repos/foo/bar/issues/1/comments") == [{"id": 1}]
        assert self.sleep.call_count == 1

    def test_permanent_5xx_exhausts_retries_and_raises(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        with patch("urllib.request.urlopen", side_effect=lambda req: (_ for _ in ()).throw(_http_error(503))):
            with pytest.raises(urllib.error.HTTPError):
                github_api("GET", "/repos/foo/bar/issues/1/comments")
        assert self.sleep.call_count == RETRY_ATTEMPTS - 1

    @pytest.mark.parametrize("code", [404, 422])
    def test_deterministic_4xx_is_not_retried(self, monkeypatch, code):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        with patch("urllib.request.urlopen", side_effect=_http_error(code)) as opener:
            with pytest.raises(urllib.error.HTTPError):
                github_api("GET", "/repos/foo/bar/issues/1/comments")
        assert opener.call_count == 1
        self.sleep.assert_not_called()

    def test_secondary_rate_limit_is_retried(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        err = _http_error(403, '{"message":"You have exceeded a secondary rate limit"}')
        ok = _urlopen_mock({"id": 7})
        with patch("urllib.request.urlopen", side_effect=[err, ok.return_value]):
            assert github_api("POST", "/repos/foo/bar/issues/1/comments", data={"body": "x"}) == {"id": 7}

    def test_plain_403_is_not_retried(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        with patch("urllib.request.urlopen", side_effect=_http_error(403, '{"message":"Resource not accessible"}')) as opener:
            with pytest.raises(urllib.error.HTTPError):
                github_api("POST", "/repos/foo/bar/issues/1/comments", data={"body": "x"})
        assert opener.call_count == 1

    def test_retry_after_header_is_honoured(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        err = _http_error(429, "slow down", headers={"Retry-After": "7"})
        ok = _urlopen_mock({"id": 7})
        with patch("urllib.request.urlopen", side_effect=[err, ok.return_value]):
            github_api("GET", "/repos/foo/bar")
        assert self.sleep.call_args[0][0] == 7.0

    def test_backoff_is_bounded(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        with patch("urllib.request.urlopen", side_effect=lambda req: (_ for _ in ()).throw(_http_error(500))):
            with pytest.raises(urllib.error.HTTPError):
                github_api("GET", "/repos/foo/bar")
        waits = [c[0][0] for c in self.sleep.call_args_list]
        assert all(0 < w <= RETRY_MAX_WAIT * 1.5 for w in waits)


class TestCommentPostingIsNonFatal:
    """Posting the summary is cosmetic: it must never fail the calling check."""

    def _args(self, tmp_path):
        content_file = tmp_path / "section.md"
        content_file.write_text("content")
        return [
            "update_pr_comment.py", "--repo", "foo/bar", "--pr", "1",
            "--section-id", "lint", "--title", "Lint", "--content-file", str(content_file),
        ]

    @pytest.mark.parametrize("exc", [
        urllib.error.HTTPError("u", 503, "Service Unavailable", email.message.Message(), None),
        urllib.error.URLError("connection reset"),
    ])
    def test_exhausted_retries_warn_and_exit_zero(self, monkeypatch, tmp_path, capsys, exc):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        monkeypatch.setattr(sys, "argv", self._args(tmp_path))
        with patch("update_pr_comment._update_comment", side_effect=exc):
            main()
        assert "Warning" in capsys.readouterr().err

    def test_unrelated_errors_still_fail(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        monkeypatch.setattr(sys, "argv", self._args(tmp_path))
        with patch("update_pr_comment._update_comment", side_effect=ValueError("bug")):
            with pytest.raises(ValueError):
                main()


class TestFindOvosComments:
    def test_returns_only_ovos_comments(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        payload = [OVOS_COMMENT, OTHER_COMMENT]
        with patch("urllib.request.urlopen", _urlopen_mock(payload)):
            result = find_ovos_comments("foo/bar", 1)
        assert len(result) == 1
        assert result[0]["id"] == 111

    def test_returns_empty_when_no_ovos_comments(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        with patch("urllib.request.urlopen", _urlopen_mock([OTHER_COMMENT])):
            result = find_ovos_comments("foo/bar", 1)
        assert result == []

    def test_returns_multiple_ovos_comments(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        second = {**OVOS_COMMENT, "id": 333}
        with patch("urllib.request.urlopen", _urlopen_mock([OVOS_COMMENT, second])):
            result = find_ovos_comments("foo/bar", 1)
        assert len(result) == 2

    def test_calls_correct_api_path(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        mock_open = _urlopen_mock([])
        with patch("urllib.request.urlopen", mock_open):
            find_ovos_comments("myorg/myrepo", 42)
        req = mock_open.call_args[0][0]
        assert "/repos/myorg/myrepo/issues/42/comments" in req.full_url


# ---------------------------------------------------------------------------
# insert_or_replace_section
# ---------------------------------------------------------------------------

class TestInsertOrReplaceSectionBackslashSafety:
    """Regression for re.error: bad escape \\x.

    build_section() embeds arbitrary generated content (e.g. raw test output)
    into `new_section`, which insert_or_replace_section previously passed
    straight to re.sub() as the replacement argument. re.sub interprets
    backslashes in its replacement string as escapes/backreferences, so
    content containing sequences like "\\x" or "\\1" (e.g. from pytest -k
    output, byte-string reprs, or bus-message payloads) crashed with
    `re.error: bad escape \\x at position N`. Observed deterministically on
    ovos-skill-volume PR #129's bus-coverage comment step.
    """

    def _existing_body(self, section_id="bus-coverage"):
        return (
            f"{COMMENT_MARKER}\n## Hi!\n\n"
            f"<!-- section:{section_id} -->\n### Old\n\nold content\n"
            f"<!-- /section:{section_id} -->\n\n---\n_Bot_"
        )

    def test_replace_with_backslash_x_does_not_raise(self):
        content = r"payload=b'\x00\x01' pattern=\x4F"
        body = self._existing_body()
        result = insert_or_replace_section(body, "bus-coverage", "Bus Coverage", content)
        assert content in result

    def test_replace_with_backreference_like_sequence_does_not_raise(self):
        content = r"regex capture group \1 matched \g<name>"
        body = self._existing_body()
        result = insert_or_replace_section(body, "bus-coverage", "Bus Coverage", content)
        assert content in result

    def test_append_path_with_backslashes_does_not_raise(self):
        """No existing section (append branch) must also survive backslashes."""
        content = r"fresh output \x00 \1"
        body = f"{COMMENT_MARKER}\n## Hi!\n\n---\n_Bot_"
        result = insert_or_replace_section(body, "bus-coverage", "Bus Coverage", content)
        assert content in result


# ---------------------------------------------------------------------------
# merge_sections
# ---------------------------------------------------------------------------

class TestMergeSections:
    def _make_body(self, sections: dict[str, str], greeting="Hi!", signature="Bot") -> str:
        lines = [COMMENT_MARKER, f"## {greeting}", ""]
        for sid, content in sections.items():
            lines += [f"<!-- section:{sid} -->", content, f"<!-- /section:{sid} -->", ""]
        lines += ["---", f"_{signature}_"]
        return "\n".join(lines)

    def test_single_body_preserved(self):
        body = self._make_body({"coverage": "### 📊 Coverage\n\n80%"})
        merged = merge_sections([body])
        assert "coverage" in merged
        assert "80%" in merged

    def test_latest_version_of_section_wins(self):
        old = self._make_body({"coverage": "### 📊 Coverage\n\n50%"})
        new = self._make_body({"coverage": "### 📊 Coverage\n\n90%"})
        merged = merge_sections([old, new])
        assert "90%" in merged
        assert "50%" not in merged

    def test_sections_from_different_bodies_are_combined(self):
        body_a = self._make_body({"coverage": "### Coverage\n\n80%"})
        body_b = self._make_body({"lint": "### Lint\n\n✅ clean"})
        merged = merge_sections([body_a, body_b])
        assert "coverage" in merged
        assert "lint" in merged
        assert "80%" in merged
        assert "✅ clean" in merged

    def test_sections_sorted_alphabetically(self):
        body = self._make_body({
            "security": "### Security\n\nok",
            "coverage": "### Coverage\n\n80%",
            "lint": "### Lint\n\nclean",
        })
        merged = merge_sections([body])
        cov_pos = merged.index("coverage")
        lint_pos = merged.index("lint")
        sec_pos = merged.index("security")
        assert cov_pos < lint_pos < sec_pos

    def test_output_contains_comment_marker(self):
        body = self._make_body({"x": "content"})
        merged = merge_sections([body])
        assert COMMENT_MARKER in merged


# ---------------------------------------------------------------------------
# deduplicate_comments
# ---------------------------------------------------------------------------

class TestDeduplicateComments:
    def _make_comments(self, count=2):
        base = {
            "body": f"{COMMENT_MARKER}\n## Hi!\n\n"
                    "<!-- section:coverage -->\n### Coverage\n\n80%\n<!-- /section:coverage -->\n\n---\n_Bot_"
        }
        return [{"id": 100 + i, **base} for i in range(count)]

    def test_patches_first_comment_with_merged_body(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        comments = self._make_comments(2)
        calls = []

        def fake_api(method, path, data=None):
            calls.append((method, path))
            return {"id": comments[0]["id"], "body": data.get("body", "") if data else ""}

        with patch("update_pr_comment.github_api", side_effect=fake_api):
            primary_id, merged = deduplicate_comments("foo/bar", 1, comments)

        assert primary_id == comments[0]["id"]
        patch_calls = [(m, p) for m, p in calls if m == "PATCH"]
        assert len(patch_calls) == 1
        assert f"/comments/{comments[0]['id']}" in patch_calls[0][1]

    def test_deletes_extra_comments(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        comments = self._make_comments(3)
        calls = []

        def fake_api(method, path, data=None):
            calls.append((method, path))
            return {}

        with patch("update_pr_comment.github_api", side_effect=fake_api):
            deduplicate_comments("foo/bar", 1, comments)

        delete_calls = [(m, p) for m, p in calls if m == "DELETE"]
        assert len(delete_calls) == 2
        deleted_ids = {int(p.split("/")[-1]) for _, p in delete_calls}
        assert deleted_ids == {comments[1]["id"], comments[2]["id"]}

    def test_returns_merged_body(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        comments = self._make_comments(2)

        with patch("update_pr_comment.github_api", return_value={}):
            _, merged = deduplicate_comments("foo/bar", 1, comments)

        assert COMMENT_MARKER in merged
        assert "coverage" in merged

    def test_delete_failure_is_swallowed(self, monkeypatch):
        """A failed DELETE on a duplicate should not abort the whole operation."""
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        comments = self._make_comments(2)

        def fake_api(method, path, data=None):
            if method == "DELETE":
                raise _http_error(404)
            return {}

        with patch("update_pr_comment.github_api", side_effect=fake_api):
            primary_id, _ = deduplicate_comments("foo/bar", 1, comments)

        assert primary_id == comments[0]["id"]


# ---------------------------------------------------------------------------
# main() — end-to-end flow
# ---------------------------------------------------------------------------

class TestMain:
    """Tests for the main() CLI entry point using a mocked GitHub API.

    Strategy: patch find_ovos_comments to control the "what comments exist" side,
    and patch github_api for write operations (POST/PATCH/DELETE). This avoids
    fighting the retry loop in main() which calls find_ovos_comments up to 6 times.
    """

    CONTENT = "Test coverage content: 85%"
    FIXED_FLAVOR = "Nice automated work!"

    def _run(self, monkeypatch, tmp_path, initial_comments, write_responses=None):
        """
        Drive main() with controlled inputs.
        - initial_comments: returned by find_ovos_comments (no retry complications)
        - write_responses: list of return values for github_api write calls
        Returns the list of (method, path, data) calls made to github_api.
        """
        content_file = tmp_path / "section.md"
        content_file.write_text(self.CONTENT)

        calls = []
        responses = list(write_responses or [])

        def fake_api(method, path, data=None):
            calls.append((method, path, data))
            if responses:
                r = responses.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r
            return {}

        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
        monkeypatch.setattr(
            "sys.argv",
            [
                "update_pr_comment.py",
                "--repo", "myorg/myrepo",
                "--pr", "7",
                "--section-id", "coverage",
                "--title", "📊 Coverage",
                "--content-file", str(content_file),
            ],
        )
        with patch("update_pr_comment.find_ovos_comments", return_value=initial_comments):
            with patch("update_pr_comment.github_api", side_effect=fake_api):
                with patch("random.choice", return_value=self.FIXED_FLAVOR):
                    main()

        return calls

    def test_creates_comment_when_none_exists(self, monkeypatch, tmp_path):
        """No existing OVOS comment → POST a new one."""
        calls = self._run(monkeypatch, tmp_path, [], [{"id": 500, "body": "created"}])
        methods = [m for m, _, _ in calls]
        assert "POST" in methods
        post_call = next((m, p, d) for m, p, d in calls if m == "POST")
        assert "/issues/7/comments" in post_call[1]
        assert "coverage" in post_call[2]["body"]
        assert self.CONTENT in post_call[2]["body"]

    def test_updates_existing_comment(self, monkeypatch, tmp_path):
        """Existing OVOS comment with different content → PATCH it."""
        existing = {
            "id": 200,
            "body": (
                f"{COMMENT_MARKER}\n## Hi!\n\n"
                "<!-- section:coverage -->\n### 📊 Coverage\n\nOld content: 40%\n"
                "<!-- /section:coverage -->\n\n---\n_Bot_"
            ),
        }
        calls = self._run(monkeypatch, tmp_path, [existing], [{}])
        methods = [m for m, _, _ in calls]
        assert "PATCH" in methods
        assert "POST" not in methods
        patch_call = next((m, p, d) for m, p, d in calls if m == "PATCH")
        assert "/comments/200" in patch_call[1]
        assert self.CONTENT in patch_call[2]["body"]

    def test_skips_update_when_content_unchanged(self, monkeypatch, tmp_path):
        """If the section body is identical after rebuild, no PATCH is issued.
        random.choice is pinned so build_section produces deterministic output."""
        with patch("random.choice", return_value=self.FIXED_FLAVOR):
            section = build_section("coverage", "📊 Coverage", self.CONTENT)
        existing = {
            "id": 300,
            "body": (
                f"{COMMENT_MARKER}\n## Hi!\n\n"
                f"{section}\n\n---\n_Bot_"
            ),
        }
        calls = self._run(monkeypatch, tmp_path, [existing])
        methods = [m for m, _, _ in calls]
        assert "PATCH" not in methods
        assert "POST" not in methods

    def test_deduplicates_when_multiple_comments_exist(self, monkeypatch, tmp_path):
        """Two OVOS comments → merge (PATCH first, DELETE second), then update."""
        body = (
            f"{COMMENT_MARKER}\n## Hi!\n\n"
            "<!-- section:coverage -->\n### 📊 Coverage\n\nOld: 50%\n"
            "<!-- /section:coverage -->\n\n---\n_Bot_"
        )
        comments = [{"id": 400, "body": body}, {"id": 401, "body": body}]
        calls = self._run(monkeypatch, tmp_path, comments, [{}, {}, {}])
        methods = [m for m, _, _ in calls]
        assert methods.count("PATCH") >= 1
        assert "DELETE" in methods

    def test_new_comment_contains_marker(self, monkeypatch, tmp_path):
        calls = self._run(monkeypatch, tmp_path, [], [{"id": 600, "body": "created"}])
        post_call = next((m, p, d) for m, p, d in calls if m == "POST")
        assert COMMENT_MARKER in post_call[2]["body"]

    def test_new_comment_contains_section_title(self, monkeypatch, tmp_path):
        calls = self._run(monkeypatch, tmp_path, [], [{"id": 601, "body": "created"}])
        post_call = next((m, p, d) for m, p, d in calls if m == "POST")
        assert "📊 Coverage" in post_call[2]["body"]
