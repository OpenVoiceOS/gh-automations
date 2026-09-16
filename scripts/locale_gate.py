"""Review-stage gate for a locale PR on one ovos-skill-* checkout.

Seven checks: parser load (with vocab loaded, not bare), basename parity
against en-US, placeholder/slot survival, reachability in the skill's own
code, dialog completeness against the names the skill's own code speaks,
resource basename compliance, and STE prose lint on any .md in scope.
Prints a per-file table, an "N in, N out" line, and exits non-zero if any
check that ran failed.

Without --base, the run is a state census: it reports what is wrong in the
tree today, with no claim about who put it there.

With --base <ref>, the gate runs twice over the same skill -- once at the
working tree (the pull request head) and once at <ref> (the pull request
base) -- and classifies every finding by identity (same file, check and
detail at both refs is one finding, never counted twice):

    introduced   present at head, absent at base -- fails the run
    pre-existing present at both -- listed, never charged, never failing
    fixed        present at base, absent at head -- listed as progress

A pre-existing finding is the skill's own defect, not the contributor's to
fix; only introduced findings fail the run.

For base_name_compliance and reachability, every finding also carries a
second, orthogonal axis -- avoidability, answering whether the author could
have done otherwise. A finding is forced by either of two relationships:

    forced (en-US mirror)  en-US already carries a file of this exact
                 basename, so the locale is obliged to mirror the name for
                 resource lookup to resolve at all -- the skill's own name is
                 wrong, not this change's to fix
    forced (same-locale pairing, OVOS-INTENT-2 SS4.3)  a '.blacklist' pairs by
                 base name with the '.intent' it suppresses or the '.entity'
                 whose values it excludes, and an '.entity' pairs by base name
                 with the '{slot}' name a same-locale '.intent' declares --
                 either way the paired resource's name already exists and the
                 file has no lawful alternative but to mirror it
    avoidable    neither relationship holds -- the author had a lawful
                 compliant name available and did not use it

Only introduced AND avoidable fails the run; introduced AND forced is
reported in its own group and does not. basename_parity, slot_survival and
dialog_completeness compare against a fixed baseline (en-US, or the skill's
own code) by construction, so avoidability does not apply to any of them.

    locale_gate.py <skill checkout path> [--locale xx-YY ...] [--md FILE ...] [--base REF]
    locale_gate.py --selftest
"""
import argparse
import contextlib
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

from ovos_spec_tools import MalformedTemplate, expand

STE_LINT = os.path.expanduser('~/.claude/skills/ste-writing/scripts/ste_lint.py')

CHECKS = ('parser_load', 'basename_parity', 'slot_survival', 'reachability',
          'dialog_completeness', 'base_name_compliance', 'prose_lint')

rows = []  # (file, locale, check, pass/fail, detail, key)
files_in = 0
files_reported = 0


def row(file, locale, check, ok, detail='', key=None, avoid=None):
    global files_reported
    result = 'pass' if ok else 'FAIL'
    rows.append((file, locale, check, result, detail, key if key is not None else detail, avoid))
    if result == 'FAIL':
        files_reported += 1


def relpath(skill_path, f):
    """Path of f relative to skill_path -- the identity and display form for
    every finding. Never an absolute path: a finding's identity, and what
    gets printed, must not depend on where the checkout happens to sit on
    disk (a throwaway --base worktree lives at a different path from the
    working tree, and is gone by the time results print), so every row is
    keyed and displayed on this form, never on the raw absolute path."""
    try:
        return os.path.relpath(os.path.abspath(f), os.path.abspath(skill_path))
    except ValueError:
        return f


def en_basenames_of(en_dir):
    """Every basename (with extension) en-US carries, recursively. None when
    there is no en-US directory to compare against."""
    if not en_dir:
        return None
    return {os.path.basename(f) for f in glob.glob(os.path.join(en_dir, '**', '*'), recursive=True)
            if os.path.isfile(f)}


def avoidability(base, locale, en_basenames):
    """'forced' when en-US already carries a file of this exact basename --
    the locale is obliged to mirror the name for resource lookup to resolve,
    so it had no lawful alternative. 'avoidable' otherwise. None when the
    notion does not apply (en-US itself, or no en-US to compare against)."""
    if locale == 'en-US' or en_basenames is None:
        return None
    return 'forced' if base in en_basenames else 'avoidable'


def pairing_forced_reason(stem, ext, locale_dir):
    """Second forcing relationship, OVOS-INTENT-2 SS4.3: '.blacklist' file is
    paired by base name with an '.intent' it suppresses, or with an
    '.entity' (or a '{slot}') whose values it excludes -- the paired
    resource's name already exists in the same locale and the blacklist has
    no lawful alternative but to mirror it. An '.entity' pairs the same way:
    its base name is the '{slot}' name a same-locale '.intent' declares, so a
    slot spelled with a capital forces the entity to mirror that spelling.
    Returns the reason string naming what it pairs with when forced, None
    when nothing in the same locale forces this name.

    '.voc' has no analogous forcing: SS4.3 gives it no paired resource whose
    pre-existing name a '.voc' file must mirror -- it is a named vocabulary
    referenced by an inline '<name>' token that the same author who names
    the '.voc' file also writes, so no external name is imposed on it.
    """
    if ext == '.blacklist':
        if os.path.isfile(os.path.join(locale_dir, stem + '.intent')):
            return f'{stem}.intent'
        if os.path.isfile(os.path.join(locale_dir, stem + '.entity')):
            return f'{stem}.entity'
        return None
    if ext == '.entity':
        for f in find_files(locale_dir, '.intent'):
            with open(f, encoding='utf-8') as fh:
                text = fh.read()
            if stem in SLOT_RE.findall(text):
                return f'{{{stem}}} slot in {os.path.basename(f)}'
        return None
    return None


LOCALE_EXTS = ('.intent', '.dialog', '.voc', '.entity', '.rx')


def find_skill_paths(root, locale_paths='', exclude=()):
    """The skill paths under root that locale_gate.py can read: the parent of
    every directory named 'locale' that holds a locale file, found the way the
    spec job finds its targets. load_locale_dirs() reads only
    <skill_path>/locale, so a skill that keeps its locale in its package
    (<package>/locale) is invisible from the repository root.

    locale_paths (space-separated) narrows the search, as the workflow input
    does for the spec job. A path named 'locale' gives its parent; any other
    path gives itself when it holds a 'locale' directory, else the skill paths
    found under it. Hidden directories and the names in exclude are skipped.
    """
    def has_locale_file(d):
        for _dirpath, _dirs, files in os.walk(d):
            if any(f.endswith(LOCALE_EXTS) for f in files):
                return True
        return False

    def search(top):
        found = []
        for dirpath, dirs, _files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in exclude)
            if os.path.basename(dirpath) == 'locale' and has_locale_file(dirpath):
                found.append(os.path.dirname(dirpath))
                dirs[:] = []
        return found

    out = []
    tops = locale_paths.split() if locale_paths else [root]
    for t in tops:
        t = t if os.path.isabs(t) else os.path.join(root, t)
        t = os.path.normpath(t)
        if os.path.basename(t) == 'locale' and os.path.isdir(t):
            if has_locale_file(t):
                out.append(os.path.dirname(t))
        elif os.path.isdir(os.path.join(t, 'locale')) and has_locale_file(os.path.join(t, 'locale')):
            out.append(t)
        elif os.path.isdir(t):
            out.extend(search(t))
    rel = []
    for p in out:
        r = os.path.relpath(p, root)
        if r not in rel:
            rel.append(r)
    return sorted(rel)


def load_locale_dirs(skill_path, wanted):
    loc_root = os.path.join(skill_path, 'locale')
    if not os.path.isdir(loc_root):
        return {}
    out = {}
    for name in sorted(os.listdir(loc_root)):
        p = os.path.join(loc_root, name)
        if os.path.isdir(p) and (not wanted or name in wanted):
            out[name] = p
    return out


def find_files(locale_dir, ext):
    return sorted(glob.glob(os.path.join(locale_dir, '**', f'*{ext}'), recursive=True))


def basenames(locale_dir, ext):
    return {os.path.basename(f) for f in find_files(locale_dir, ext)}


def load_vocab(locale_dir):
    """.voc and .entity basenames (without extension) -> list of lines."""
    vocab = {}
    for ext in ('.voc', '.entity'):
        for f in find_files(locale_dir, ext):
            name = os.path.splitext(os.path.basename(f))[0]
            with open(f, encoding='utf-8') as fh:
                lines = [l.strip() for l in fh if l.strip() and not l.startswith('#')]
            vocab[name] = lines
    return vocab


def check_parser_load(locale, locale_dir, ran, skill_path):
    intents = find_files(locale_dir, '.intent')
    if not intents:
        return
    ran.add('parser_load')
    vocab = load_vocab(locale_dir)
    for f in intents:
        rel = relpath(skill_path, f)
        with open(f, encoding='utf-8') as fh:
            lines = [l.rstrip('\n') for l in fh if l.strip()]
        for line in lines:
            try:
                expand(line, vocab)
                row(rel, locale, 'parser_load', True, key=(rel, line))
            except MalformedTemplate as e:
                row(rel, locale, 'parser_load', False, f'{line!r}: {e}', key=(rel, line))


def check_basename_parity(locale, locale_dir, en_dir, ran, skill_path):
    ran.add('basename_parity')
    rel_dir = relpath(skill_path, locale_dir)
    any_bad = False
    for ext in ('.intent', '.dialog', '.voc'):
        en = basenames(en_dir, ext)
        loc = basenames(locale_dir, ext)
        for name in sorted(en - loc):
            row(rel_dir, locale, f'basename_parity{ext}', False,
                f'missing: {name}', key=('missing', ext, name))
            any_bad = True
        for name in sorted(loc - en):
            row(rel_dir, locale, f'basename_parity{ext}', False,
                f'extra: {name}', key=('extra', ext, name))
            any_bad = True
    if not any_bad:
        row(rel_dir, locale, 'basename_parity', True, key=('ok',))


SLOT_RE = re.compile(r'\{([a-zA-Z0-9_]+)\}')
VOC_RE = re.compile(r'<([a-zA-Z0-9_]+)>')


def _by_basename(locale_dir, ext):
    return {os.path.basename(f): f for f in find_files(locale_dir, ext)}


def check_slot_survival(locale, locale_dir, en_dir, ran, skill_path):
    """OVOS-INTENT-2 SS4.2: every phrase in a file MUST declare the same SET
    of named slots -- a rule about a file, not about two languages, and a
    set rather than a count. A locale is free to carry more (or fewer)
    template lines than en-US; comparing occurrence counts across the whole
    file would fail any locale whose line count differs from en-US even
    when every locale phrase uses exactly the slot set en-US uses. So this
    compares the slot SET a locale file uses against the slot SET en-US
    uses, and reports the two directions separately, because they mean
    different things: dropping a slot en-US has means a value the skill
    supplies is never spoken or captured; using one en-US does not have
    means the locale expects a value nothing fills. The same set-not-count
    comparison applies to <voc> vocabulary references.
    """
    en_by_name = _by_basename(en_dir, '.intent')
    loc_by_name = _by_basename(locale_dir, '.intent')
    shared = sorted(set(en_by_name) & set(loc_by_name))
    if not shared:
        return
    ran.add('slot_survival')
    for name in shared:
        en_text = open(en_by_name[name], encoding='utf-8').read()
        loc_text = open(loc_by_name[name], encoding='utf-8').read()
        en_slots = set(SLOT_RE.findall(en_text))
        loc_slots = set(SLOT_RE.findall(loc_text))
        en_vocs = set(VOC_RE.findall(en_text))
        loc_vocs = set(VOC_RE.findall(loc_text))
        dropped_slots = sorted(en_slots - loc_slots)
        extra_slots = sorted(loc_slots - en_slots)
        dropped_vocs = sorted(en_vocs - loc_vocs)
        extra_vocs = sorted(loc_vocs - en_vocs)
        f = relpath(skill_path, loc_by_name[name])
        clean = True
        if dropped_slots:
            clean = False
            row(f, locale, 'slot_survival', False,
                f'drops slot(s) en-US declares: {dropped_slots}', key=(name, 'slots', 'dropped'))
        if extra_slots:
            clean = False
            row(f, locale, 'slot_survival', False,
                f'uses slot(s) en-US does not declare: {extra_slots}', key=(name, 'slots', 'extra'))
        if dropped_vocs:
            clean = False
            row(f, locale, 'slot_survival', False,
                f'drops <voc>(s) en-US declares: {dropped_vocs}', key=(name, 'vocs', 'dropped'))
        if extra_vocs:
            clean = False
            row(f, locale, 'slot_survival', False,
                f'uses <voc>(s) en-US does not declare: {extra_vocs}', key=(name, 'vocs', 'extra'))
        if clean:
            row(f, locale, 'slot_survival', True, key=(name, 'ok'))


INTENT_HANDLER_RE = re.compile(r'intent_handler\(\s*["\']([^"\']+\.intent)["\']')
REGISTER_INTENT_RE = re.compile(r'register_intent_file\(\s*["\']([^"\']+\.intent)["\']')
SPEAK_DIALOG_RE = re.compile(r'speak_dialog\(\s*["\']([^"\']+)["\']')
SPEAK_DIALOG_CALL_RE = re.compile(r'speak_dialog\(\s*([^)]*)')
COMMON_QUERY_RE = re.compile(r'CommonQuerySkill|@common_query')
BASE_NAME_RE = re.compile(r'^[a-z0-9_]+$')


def load_skill_code(skill_path):
    src = []
    for f in glob.glob(os.path.join(skill_path, '**', '*.py'), recursive=True):
        rel = os.path.relpath(f, skill_path)
        if 'test' in rel.split(os.sep) or os.path.basename(rel).startswith('test'):
            continue
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                src.append(fh.read())
        except OSError:
            pass
    return '\n'.join(src)


def has_dynamic_speak_dialog(code):
    """True if any speak_dialog(...) call's first argument is not a string literal.

    A name assembled at runtime (a variable, an attribute like dialog.name, an
    f-string) defeats static enumeration entirely -- there is no literal to grep.
    """
    for call in SPEAK_DIALOG_CALL_RE.findall(code):
        first_arg = call.split(',', 1)[0].strip()
        if not first_arg:
            continue
        if not (first_arg.startswith('"') or first_arg.startswith("'")):
            return True
    return False


def check_reachability(locale, locale_dir, skill_path, code, ran, en_basenames=None):
    intents = set(INTENT_HANDLER_RE.findall(code)) | set(REGISTER_INTENT_RE.findall(code))
    dialogs = {f'{n}.dialog' for n in SPEAK_DIALOG_RE.findall(code)}
    if not intents and not dialogs:
        row(relpath(skill_path, locale_dir), locale, 'reachability', True,
            'no file-intent registrations found, out of scope', key=('vacuous',))
        return
    ran.add('reachability')
    common_query = bool(COMMON_QUERY_RE.search(code))
    dynamic_dialog = has_dynamic_speak_dialog(code)
    if dynamic_dialog:
        ran.add('reachability_degraded')
    for f in find_files(locale_dir, '.intent'):
        name = os.path.basename(f)
        rel = relpath(skill_path, f)
        if name in intents:
            row(rel, locale, 'reachability', True, key=('intent', name))
        elif common_query:
            row(rel, locale, 'reachability', True,
                'unreachable (common-query skill, review by hand)', key=('intent', name))
        else:
            row(rel, locale, 'reachability', False, f'{name} not registered', key=('intent', name),
                avoid=avoidability(name, locale, en_basenames))
    for f in find_files(locale_dir, '.dialog'):
        name = os.path.basename(f)
        rel = relpath(skill_path, f)
        if name in dialogs:
            row(rel, locale, 'reachability', True, key=('dialog', name))
        elif common_query:
            row(rel, locale, 'reachability', True,
                'unreachable (common-query skill, review by hand)', key=('dialog', name))
        elif dynamic_dialog:
            row(rel, locale, 'reachability', True,
                'unreachable (dialog name built at runtime, review by hand)', key=('dialog', name))
        else:
            row(rel, locale, 'reachability', False, f'{name} not spoken', key=('dialog', name),
                avoid=avoidability(name, locale, en_basenames))


def check_base_name_compliance(locale, locale_dir, skill_path, ran, en_basenames=None):
    ran.add('base_name_compliance')
    for f in glob.glob(os.path.join(locale_dir, '**', '*'), recursive=True):
        if not os.path.isfile(f):
            continue
        base = os.path.basename(f)
        stem, ext = os.path.splitext(base)
        rel = relpath(skill_path, f)
        if BASE_NAME_RE.match(stem) and ext == ext.lower():
            row(rel, locale, 'base_name_compliance', True, key=rel)
        else:
            avoid = avoidability(base, locale, en_basenames)
            detail = f'{base!r} does not match ^[a-z0-9_]+$ + lowercase extension (OVOS-INTENT-2 SS2)'
            pairing = pairing_forced_reason(stem, ext, locale_dir)
            if pairing:
                avoid = 'forced'
                detail += f'; forced: pairs with {pairing} (OVOS-INTENT-2 SS4.3)'
            row(rel, locale, 'base_name_compliance', False, detail, key=rel, avoid=avoid)


DIALOG_CALL_RE = re.compile(r'\b(?:self\.)?(speak_dialog|get_response)\s*\(')


def split_top_level(s):
    """Split s on top-level commas, respecting nesting of (), [], {} and
    quoted strings. Used to pull apart a call's argument list without a full
    parser -- good enough for the literal-first-argument, kwarg-or-dict-second
    shapes this fleet actually writes."""
    if s.strip() == '':
        return []
    parts = []
    depth = 0
    quote = None
    cur = []
    for i, c in enumerate(s):
        if quote:
            cur.append(c)
            if c == quote and s[i - 1] != '\\':
                quote = None
        elif c in '"\'':
            quote = c
            cur.append(c)
        elif c in '([{':
            depth += 1
            cur.append(c)
        elif c in ')]}':
            depth -= 1
            cur.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append(''.join(cur))
    return parts


def find_dialog_calls(code):
    """Every speak_dialog(...)/get_response(...) call in the skill's own
    code, as (kind, name, arg_parts). name is the dialog name when the first
    argument is a string literal, None when it is assembled at runtime (a
    variable, an attribute, an f-string) -- that call can never be checked
    statically. arg_parts is the top-level split of every argument after the
    name, for the slot-supply check.
    """
    calls = []
    for m in DIALOG_CALL_RE.finditer(code):
        kind = m.group(1)
        start = m.end() - 1
        depth = 0
        end = None
        i = start
        while i < len(code):
            if code[i] == '(':
                depth += 1
            elif code[i] == ')':
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end is None:
            continue
        parts = split_top_level(code[start + 1:end])
        if not parts:
            continue
        first = parts[0].strip()
        lit = re.match(r'''^["']([^"']+)["']$''', first)
        calls.append((kind, lit.group(1) if lit else None, parts[1:]))
    return calls


def parse_call_args(arg_parts):
    """Slot names a call site appears to supply, plus whether any argument
    defeats static resolution. A bare variable or an unrecognised expression
    makes the call UNKNOWN rather than accusing it of a missing slot --
    under-reporting here is the point: a false accusation blocks correct
    work, a miss is just a blind spot.
    """
    supplied = set()
    unknown = False
    for p in arg_parts:
        p = p.strip()
        if not p:
            continue
        m = re.match(r'^([A-Za-z_]\w*)\s*=\s*(.*)$', p, re.S)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key in ('data', 'kwargs'):
                dict_keys = re.findall(r'''['"]([A-Za-z_]\w*)['"]\s*:''', val)
                call_keys = re.findall(r'([A-Za-z_]\w*)\s*=', val) if val.startswith('dict(') else []
                if dict_keys or call_keys:
                    supplied.update(dict_keys)
                    supplied.update(call_keys)
                elif val not in ('{}', 'dict()'):
                    unknown = True
            else:
                supplied.add(key)
        else:
            dict_keys = re.findall(r'''['"]([A-Za-z_]\w*)['"]\s*:''', p)
            if dict_keys:
                supplied.update(dict_keys)
            elif p != '{}':
                unknown = True
    return supplied, unknown


FUNC_DEF_RE = re.compile(r'^\s*def\s+\w+\s*\(')
FUNC_DECORATOR_RE = re.compile(r'^\s*@intent_handler\(\s*["\']([^"\']+\.intent)["\']\s*\)\s*$')


def split_functions(code):
    """Chop the skill's source into (gating_intent_or_None, body) chunks, one
    per method: gating_intent is the '<name>.intent' an @intent_handler
    decorator names immediately above a def, None for a method reached some
    other way (an event handler, a helper, a plain call). A method's body
    runs from its def line up to the next def or @intent_handler line --
    an approximation, not a parser, but the shape every skill in this fleet
    actually writes.
    """
    lines = code.split('\n')
    funcs = []
    i, n = 0, len(lines)
    while i < n:
        m = FUNC_DECORATOR_RE.match(lines[i])
        decorator = m.group(1) if m else None
        if decorator:
            i += 1
            if i >= n:
                break
        if FUNC_DEF_RE.match(lines[i]):
            start = i
            i += 1
            while i < n and not FUNC_DEF_RE.match(lines[i]) and not FUNC_DECORATOR_RE.match(lines[i]):
                i += 1
            funcs.append((decorator, '\n'.join(lines[start:i])))
        else:
            i += 1
    return funcs


def dialog_reachability(code):
    """Which dialog names the skill's code speaks unconditionally (from a
    method no @intent_handler gates -- an event handler, common-query
    callback, or helper reached some other way) versus which are spoken only
    from behind a specific per-locale intent file. A dialog gated by
    'are_you_ready.intent' is dead code in a locale that does not carry that
    intent file yet -- not this check's business until the intent arrives,
    which is the exact moment a pull request like
    ovos-skill-boot-finished#99 makes it a live gap instead of dead code.

    Falls back to treating every spoken name as unconditional when the
    source does not parse into recognisable methods (never invents a
    reachability claim it cannot support).
    """
    funcs = split_functions(code)
    unconditional = set()
    gated = {}  # dialog name -> set of gating '<name>.intent' filenames
    any_dynamic = False
    if not funcs:
        for _kind, name, _args in find_dialog_calls(code):
            if name is None:
                any_dynamic = True
            else:
                unconditional.add(name)
        return unconditional, gated, any_dynamic
    for decorator, body in funcs:
        for _kind, name, _args in find_dialog_calls(body):
            if name is None:
                any_dynamic = True
            elif decorator:
                gated.setdefault(name, set()).add(decorator)
            else:
                unconditional.add(name)
    return unconditional, gated, any_dynamic


def check_dialog_completeness(locale, locale_dir, skill_path, dialog_info, ran):
    """A pull request can add an intent whose handler speaks a dialog by
    name that does not exist in the locale it targets -- every other check
    passes such a change (the intent basename is present, basename_parity
    improves, nothing routes to complete_intent_failure), and the renderer
    then speaks the literal dialog key to the user, which is worse than the
    gap it replaced (ovos-skill-boot-finished#99, ovos-skill-parrot#128).
    This asks the question none of the others do: for every dialog name the
    skill's own code speaks (speak_dialog, and get_response which this fleet
    also uses to speak a dialog) that this locale can actually reach, does
    the file exist here, and does the call site appear to supply every slot
    the file declares.

    A CommonQuerySkill's @common_query handler still calls speak_dialog like
    any other, so it needs no special case here -- unlike reachability, this
    check never depends on whether an intent got registered; it only asks
    whether the dialog is reachable at all, unconditionally or through an
    intent this locale carries.
    """
    calls, unconditional, gated, any_dynamic = dialog_info
    if not calls:
        return
    ran.add('dialog_completeness')
    if any_dynamic:
        ran.add('dialog_completeness_degraded')
    by_name = {}
    for _kind, name, arg_parts in calls:
        if name is not None:
            by_name.setdefault(name, []).append(arg_parts)
    locale_intents = basenames(locale_dir, '.intent')
    reachable = set(unconditional)
    for name, gating_intents in gated.items():
        if name in reachable:
            continue
        if gating_intents & locale_intents:
            reachable.add(name)
    existing = _by_basename(locale_dir, '.dialog')
    rel_dir = relpath(skill_path, locale_dir)
    for name in sorted(reachable & set(by_name)):
        dialog_file = f'{name}.dialog'
        if dialog_file not in existing:
            row(rel_dir, locale, 'dialog_completeness', False,
                f'{dialog_file} spoken by skill but missing in {locale}', key=('missing', name))
            continue
        row(rel_dir, locale, 'dialog_completeness', True, key=('present', name))
        f = existing[dialog_file]
        dialog_slots = set(SLOT_RE.findall(open(f, encoding='utf-8').read()))
        if not dialog_slots:
            continue
        # Each call site is checked on its own: a complete call must not
        # mask a second call that omits a slot.
        missing_known = set()
        missing_unknown = set()
        for arg_parts in by_name[name]:
            s, u = parse_call_args(arg_parts)
            gap = dialog_slots - s
            if not gap:
                continue
            if u:
                missing_unknown |= gap
            else:
                missing_known |= gap
        missing_unknown -= missing_known
        rel_f = relpath(skill_path, f)
        if missing_known:
            missing = sorted(missing_known)
            row(rel_f, locale, 'dialog_completeness_slots', False,
                f'{dialog_file}: call does not appear to supply slot(s) {missing}',
                key=('slots', name, tuple(missing)))
        if missing_unknown:
            missing = sorted(missing_unknown)
            row(rel_f, locale, 'dialog_completeness_slots_unknown', True,
                f'{dialog_file}: slot(s) {missing} not confirmed supplied '
                f'(call passes an argument that cannot be resolved statically)',
                key=('unknown', name, tuple(missing)))


def check_prose_lint(md_files, skill_path, ran):
    if not md_files:
        return
    ran.add('prose_lint')
    for f in md_files:
        try:
            abs_skill = os.path.abspath(skill_path)
            abs_f = os.path.abspath(f)
            key = relpath(skill_path, f) \
                if os.path.commonpath([abs_skill, abs_f]) == abs_skill else abs_f
        except ValueError:
            key = os.path.abspath(f)
        try:
            out = subprocess.run([sys.executable, STE_LINT, f],
                                  capture_output=True, text=True, timeout=60)
        except OSError as e:
            row(key, '-', 'prose_lint', False, f'lint could not run: {e}', key=key)
            continue
        ok = out.returncode == 0
        row(key, '-', 'prose_lint', ok,
            '' if ok else (out.stdout + out.stderr).strip()[:400], key=key)


def collect(skill_path, wanted_locales, md_files):
    """Run all checks once over skill_path and return a snapshot, leaving the
    module-level accumulators reset for the next caller."""
    global rows, files_in, files_reported
    rows, files_in, files_reported = [], 0, 0
    ran = set()

    locale_dirs = load_locale_dirs(skill_path, set(wanted_locales) if wanted_locales else None)
    # en-US is always loaded as the comparison baseline, even when a --locale
    # filter excludes it from the directories under review -- a --locale
    # filter selects what is JUDGED, never what is available for comparison.
    en_dir = load_locale_dirs(skill_path, None).get('en-US')
    en_basenames = en_basenames_of(en_dir)
    code = load_skill_code(skill_path)
    dialog_calls = find_dialog_calls(code)
    unconditional, gated, any_dynamic = dialog_reachability(code)
    dialog_info = (dialog_calls, unconditional, gated, any_dynamic)

    for locale, ldir in locale_dirs.items():
        files_in += sum(1 for f in glob.glob(os.path.join(ldir, '**', '*'), recursive=True)
                         if os.path.isfile(f))
        check_parser_load(locale, ldir, ran, skill_path)
        if en_dir and locale != 'en-US':
            check_basename_parity(locale, ldir, en_dir, ran, skill_path)
            check_slot_survival(locale, ldir, en_dir, ran, skill_path)
        check_reachability(locale, ldir, skill_path, code, ran, en_basenames)
        check_dialog_completeness(locale, ldir, skill_path, dialog_info, ran)
        check_base_name_compliance(locale, ldir, skill_path, ran, en_basenames)

    check_prose_lint(md_files or [], skill_path, ran)

    return list(rows), files_in, files_reported, ran


def _print_table(skill_path, rows_):
    # every row's file field is already checkout-relative, computed at the
    # time the finding was made -- never recomputed here against whatever
    # happens to still exist on disk (a --base worktree is gone by the time
    # this prints).
    print(f'{"file":<55} {"locale":<8} {"check":<18} {"result":<12} detail')
    for r in rows_:
        f, locale, check, result, detail = r[0], r[1], r[2], r[3], r[4]
        print(f'{f:<55} {locale:<8} {check:<18} {result:<12} {detail}')


def _checkout_base(skill_path, ref):
    """Materialize the merge-base of HEAD and <ref>, in the git repo owning
    skill_path, in a throwaway worktree, and return (base_skill_path,
    cleanup). Read-only: worktree add of a local ref, never a push/fetch of
    anything new.

    The comparison point is the merge-base, not <ref>'s own tip: <ref> (the
    PR's target branch) keeps moving after a PR forks from it, and any
    unrelated fix landed there since the fork makes an old, real,
    pre-existing defect vanish from the "base" run -- which would then
    misreport it as introduced by a PR that never touched it. Diffing
    against the commit the PR actually branched from is what "the PR's own
    change" means.
    """
    skill_path = os.path.abspath(skill_path)
    root = subprocess.run(['git', '-C', skill_path, 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True, check=True).stdout.strip()
    rel = os.path.relpath(skill_path, root)
    head = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                           capture_output=True, text=True, check=True).stdout.strip()
    merge_base = subprocess.run(['git', '-C', root, 'merge-base', head, ref],
                                 capture_output=True, text=True, check=True).stdout.strip()
    wt = tempfile.mkdtemp(prefix='localegate-base-')
    subprocess.run(['git', '-C', root, 'worktree', 'add', '--detach', wt, merge_base],
                    capture_output=True, text=True, check=True)
    base_skill_path = os.path.normpath(os.path.join(wt, rel))

    def cleanup():
        subprocess.run(['git', '-C', root, 'worktree', 'remove', '--force', wt],
                        capture_output=True, text=True)
        shutil.rmtree(wt, ignore_errors=True)

    return base_skill_path, cleanup


def run_gate(skill_path, wanted_locales, md_files, base_ref=None):
    head_rows, head_in, head_out, ran = collect(skill_path, wanted_locales, md_files)

    if not base_ref:
        _print_table(skill_path, head_rows)
        print(f'{head_in} in, {head_out} out')
        print('census: no --base given, findings below are unattributed tree state, not a verdict on who added them')
        failed = False
        for c in CHECKS:
            if c in ran:
                c_rows = [r for r in head_rows if r[2] == c or r[2].startswith(c)]
                c_failed = any(r[3] == 'FAIL' for r in c_rows)
                degraded = (c == 'reachability' and 'reachability_degraded' in ran) or \
                    (c == 'dialog_completeness' and 'dialog_completeness_degraded' in ran)
                if c_failed:
                    print(f'check {c}: RAN, FAIL')
                    failed = True
                elif degraded:
                    reason = 'dialog names built at runtime, reachability unverifiable, reviewed by hand' \
                        if c == 'reachability' else \
                        'dialog names built at runtime, dialog completeness unverifiable for those calls, reviewed by hand'
                    print(f'check {c}: RAN, DEGRADED ({reason})')
                else:
                    print(f'check {c}: RAN, pass')
            else:
                print(f'check {c}: VACUOUS (nothing to read)')
        return 1 if failed else 0

    base_skill_path, cleanup = _checkout_base(skill_path, base_ref)
    try:
        base_md = []
        for f in (md_files or []):
            f_abs = os.path.abspath(f)
            if f_abs.startswith(os.path.abspath(skill_path)):
                base_md.append(os.path.join(base_skill_path, os.path.relpath(f_abs, skill_path)))
            else:
                base_md.append(f_abs)
        base_rows, _base_in, _base_out, base_ran = collect(base_skill_path, wanted_locales, base_md)
    finally:
        cleanup()

    def fail_ids(rows_):
        return {(r[1], r[2], r[5]): r for r in rows_ if r[3] == 'FAIL'}

    head_fail = fail_ids(head_rows)
    base_fail = fail_ids(base_rows)
    introduced_ids = set(head_fail) - set(base_fail)
    pre_ids = set(head_fail) & set(base_fail)
    fixed_ids = set(base_fail) - set(head_fail)

    # avoidability is a property of the file/basename at head, orthogonal to
    # attribution: it applies only to base_name_compliance and reachability,
    # where en-US carrying the same basename means the locale had no lawful
    # alternative to the name it copied.
    AVOID_CHECKS = ('base_name_compliance', 'reachability')

    def is_avoid_check(check_name):
        return any(check_name == c or check_name.startswith(c) for c in AVOID_CHECKS)

    display_rows = []
    for r in head_rows:
        ident = (r[1], r[2], r[5])
        if r[3] != 'FAIL':
            display_rows.append(r)
        elif ident in introduced_ids:
            label = 'introduced'
            if is_avoid_check(r[2]) and r[6]:
                label = f'introduced, {r[6]}'
            display_rows.append((r[0], r[1], r[2], label, r[4], r[5], r[6]))
        else:
            display_rows.append((r[0], r[1], r[2], 'pre-existing', r[4], r[5], r[6]))
    for ident in fixed_ids:
        r = base_fail[ident]
        display_rows.append((r[0], r[1], r[2], 'fixed', r[4], r[5], r[6]))

    global rows
    rows = display_rows

    _print_table(skill_path, display_rows)
    print(f'{head_in} in, {head_out} out')
    print(f'differential against {base_ref}: pre-existing findings are the skill\'s own, not this change\'s to fix')
    print("'introduced, forced' findings are the skill's own name being wrong, mirrored because resource lookup "
          "is by basename -- fixing one means renaming en-US and every locale together, in a different pull "
          "request, and does not fail the run")

    failed = False
    for c in CHECKS:
        ran_either = c in ran or c in base_ran
        if not ran_either:
            print(f'check {c}: VACUOUS (nothing to read)')
            continue
        c_introduced = {i for i in introduced_ids if i[1] == c or i[1].startswith(c)}
        c_pre = {i for i in pre_ids if i[1] == c or i[1].startswith(c)}
        c_fixed = {i for i in fixed_ids if i[1] == c or i[1].startswith(c)}
        degraded = (c == 'reachability' and ('reachability_degraded' in ran or 'reachability_degraded' in base_ran)) or \
            (c == 'dialog_completeness' and
             ('dialog_completeness_degraded' in ran or 'dialog_completeness_degraded' in base_ran))
        if degraded:
            reason = 'dialog names built at runtime, reachability unverifiable, reviewed by hand' \
                if c == 'reachability' else \
                'dialog names built at runtime, dialog completeness unverifiable for those calls, reviewed by hand'
            suffix = f', DEGRADED ({reason})'
        else:
            suffix = ''
        if is_avoid_check(c):
            c_forced = {i for i in c_introduced if head_fail[i][6] == 'forced'}
            c_avoidable = c_introduced - c_forced
            print(f'check {c}: RAN, {len(c_avoidable)} introduced avoidable, {len(c_forced)} introduced forced, '
                  f'{len(c_pre)} pre-existing, {len(c_fixed)} fixed{suffix}')
            if c_avoidable:
                failed = True
        else:
            print(f'check {c}: RAN, {len(c_introduced)} introduced, {len(c_pre)} pre-existing, {len(c_fixed)} fixed{suffix}')
            if c_introduced:
                failed = True

    return 1 if failed else 0


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------

def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _build_clean_tree(root):
    en = os.path.join(root, 'locale', 'en-US')
    pt = os.path.join(root, 'locale', 'pt-PT')
    _write(os.path.join(en, 'hello.intent'), 'hello {name}\n')
    _write(os.path.join(en, 'greet.dialog'), 'hello there\n')
    _write(os.path.join(en, 'greeting.voc'), 'hello\nhi\n')
    _write(os.path.join(pt, 'hello.intent'), 'ola {name}\n')
    _write(os.path.join(pt, 'greet.dialog'), 'ola pessoal\n')
    _write(os.path.join(pt, 'greeting.voc'), 'ola\noi\n')
    _write(os.path.join(root, '__init__.py'),
           'from ovos_workshop.skills import OVOSSkill\n'
           'class S(OVOSSkill):\n'
           '    @intent_handler("hello.intent")\n'
           '    def h(self, m):\n'
           '        self.speak_dialog("greet")\n')


def _git(root, *args):
    subprocess.run(['git', '-C', root, *args], check=True, capture_output=True, text=True)


def _git_commit_all(root, message):
    _git(root, 'add', '-A')
    _git(root, '-c', 'user.email=test@example.com', '-c', 'user.name=Test',
         'commit', '-m', message, '--quiet')


def selftest():
    ok = True

    def expect_fail(name, root, reason_substr, locales=None):
        nonlocal ok
        global rows, files_in, files_reported
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, locales or [], [])
        failing_details = ' | '.join(r[4] for r in rows if r[3] == 'FAIL')
        if code == 0:
            print(f'SELFTEST FAIL [{name}]: expected non-zero exit, got 0')
            ok = False
        elif reason_substr not in failing_details:
            print(f'SELFTEST FAIL [{name}]: expected reason {reason_substr!r} not found in: {failing_details}')
            ok = False
        else:
            print(f'SELFTEST OK [{name}]: {reason_substr!r} found')

    def expect_pass(name, root, locales=None):
        nonlocal ok
        global rows, files_in, files_reported
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, locales or [], [])
        if code != 0:
            print(f'SELFTEST FAIL [{name}]: expected clean pass, got exit {code}')
            ok = False
        else:
            print(f'SELFTEST OK [{name}]: clean tree passed')

    with tempfile.TemporaryDirectory(prefix='localegate-clean-') as root:
        _build_clean_tree(root)
        expect_pass('clean tree', root)

    # 1. parser load: malformed .intent line (undefined vocab reference)
    with tempfile.TemporaryDirectory(prefix='localegate-parser-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'),
               'ola {name} <undefined_voc>\n')
        expect_fail('malformed .intent', root, 'undefined vocabulary')

    # 2. basename parity: locale missing an en-US basename
    with tempfile.TemporaryDirectory(prefix='localegate-parity-') as root:
        _build_clean_tree(root)
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        expect_fail('missing basename', root, 'missing:')

    # 3. slot survival: template drops a {slot}
    with tempfile.TemporaryDirectory(prefix='localegate-slot-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'), 'ola\n')
        expect_fail('dropped slot', root, "drops slot(s) en-US declares: ['name']")

    # 4. reachability: a .dialog no code speaks, introduced only in the locale
    with tempfile.TemporaryDirectory(prefix='localegate-reach-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'orphan.dialog'), 'ninguem me fala\n')
        expect_fail('unspoken dialog', root, 'not spoken')

    global rows, files_in, files_reported

    # 4b. reachability: dialog name built at runtime must WARN, not fail
    with tempfile.TemporaryDirectory(prefix='localegate-dynreach-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'runtime.dialog'), 'built at runtime\n')
        _write(os.path.join(root, 'locale', 'pt-PT', 'runtime.dialog'), 'construido em runtime\n')
        _write(os.path.join(root, '__init__.py'),
               'from ovos_workshop.skills import OVOSSkill\n'
               'class S(OVOSSkill):\n'
               '    @intent_handler("hello.intent")\n'
               '    def h(self, m):\n'
               '        dialog = self.pick()\n'
               '        self.speak_dialog(dialog.name)\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [])
        details = ' | '.join(r[4] for r in rows)
        failing = [r for r in rows if r[2] == 'reachability' and r[3] == 'FAIL']
        if code != 0:
            print(f'SELFTEST FAIL [dynamic dialog name]: expected run not to fail on this, got exit {code}')
            ok = False
        elif failing:
            print(f'SELFTEST FAIL [dynamic dialog name]: reachability still hard-failed: {failing}')
            ok = False
        elif 'dialog name built at runtime' not in details:
            print(f'SELFTEST FAIL [dynamic dialog name]: expected warn reason not found in: {details}')
            ok = False
        else:
            print('SELFTEST OK [dynamic dialog name]: warned without failing the run')

    # 4c. base_name_compliance: a space and a capital in a resource basename must FAIL
    with tempfile.TemporaryDirectory(prefix='localegate-basename-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'bad name.dialog'), 'has a space\n')
        _write(os.path.join(root, 'locale', 'en-US', 'BadName.dialog'), 'has a capital\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [])
        failing_names = {os.path.basename(r[0]) for r in rows
                          if r[2] == 'base_name_compliance' and r[3] == 'FAIL'}
        if code == 0:
            print('SELFTEST FAIL [base_name_compliance]: expected non-zero exit, got 0')
            ok = False
        elif not {'bad name.dialog', 'BadName.dialog'} <= failing_names:
            print(f'SELFTEST FAIL [base_name_compliance]: expected both offenders named, got {failing_names}')
            ok = False
        else:
            print(f'SELFTEST OK [base_name_compliance]: {failing_names} named')

    # 4d. base_name_compliance census (no --base): a bad name en-US also carries
    # is no longer exempted -- retiring the en-US-mirroring heuristic means
    # every offender fails a plain census, mirrored or not.
    with tempfile.TemporaryDirectory(prefix='localegate-census-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'BadName.dialog'), 'has a capital\n')
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadName.dialog'), 'tem uma maiuscula\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [])
        pt_rows = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                   and os.path.basename(r[0]) == 'BadName.dialog']
        if code == 0:
            print('SELFTEST FAIL [census no exemption]: expected non-zero exit, got 0')
            ok = False
        elif not pt_rows or pt_rows[0][3] != 'FAIL':
            print(f'SELFTEST FAIL [census no exemption]: expected a FAIL row, got {pt_rows}')
            ok = False
        else:
            print('SELFTEST OK [census no exemption]: en-US carrying the same bad name no longer exempts it')

    # 4e. base_name_compliance: an offender introduced only in the locale must fail
    with tempfile.TemporaryDirectory(prefix='localegate-introduced-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadOnly.dialog'), 'so aqui\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [])
        pt_rows = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                   and os.path.basename(r[0]) == 'BadOnly.dialog']
        if code == 0:
            print('SELFTEST FAIL [introduced base_name]: expected non-zero exit, got 0')
            ok = False
        elif not pt_rows or pt_rows[0][3] != 'FAIL':
            print(f'SELFTEST FAIL [introduced base_name]: expected a FAIL row, got {pt_rows}')
            ok = False
        else:
            print(f'SELFTEST OK [introduced base_name]: {pt_rows[0][4]!r} found, run failed')

    # 5. prose lint: a .md that trips STE lint
    with tempfile.TemporaryDirectory(prefix='localegate-md-') as root:
        _build_clean_tree(root)
        bad_md = os.path.join(root, 'README.md')
        _write(bad_md,
               'This functionality will basically allow the user to potentially '
               'utilize the system in order to facilitate a seamless experience, '
               'and, as a result, this could in some cases enable additional '
               'functionality that may be leveraged going forward.\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [bad_md])
        failing_details = ' | '.join(r[4] for r in rows if r[3] == 'FAIL')
        if code == 0:
            print('SELFTEST FAIL [ste lint]: expected non-zero exit, got 0')
            ok = False
        elif not failing_details:
            print('SELFTEST FAIL [ste lint]: expected a lint failure reason, got none')
            ok = False
        else:
            print(f'SELFTEST OK [ste lint]: {failing_details[:120]!r} found')

    # 6. basename_parity must RUN under --locale scoping, comparing against
    # en-US even though en-US itself is not among the named locales.
    with tempfile.TemporaryDirectory(prefix='localegate-scopedparity-') as root:
        _build_clean_tree(root)
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        expect_fail('scoped basename_parity', root, 'missing:', locales=['pt-PT'])

    # 7. slot_survival must RUN under --locale scoping, same baseline.
    with tempfile.TemporaryDirectory(prefix='localegate-scopedslot-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'), 'ola\n')
        expect_fail('scoped slot_survival', root, "drops slot(s) en-US declares: ['name']", locales=['pt-PT'])

    # prose_lint vacuous when no .md passed
    with tempfile.TemporaryDirectory(prefix='localegate-vacuous-') as root:
        _build_clean_tree(root)
        rows, files_in, files_reported = [], 0, 0
        run_gate(root, [], [])

    # 8. differential: a defect present at base and head is pre-existing and
    # must not fail the run.
    with tempfile.TemporaryDirectory(prefix='localegate-diffpre-') as root:
        _build_clean_tree(root)
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: pt-PT missing greet.dialog')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head == base here: nothing changed since the base commit.
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2].startswith('basename_parity') and r[1] == 'pt-PT'
                   and 'greet.dialog' in r[4]]
        if not matches or matches[0][3] != 'pre-existing':
            print(f'SELFTEST FAIL [differential pre-existing]: expected a pre-existing row, got {matches}')
            ok = False
        elif code != 0:
            print(f'SELFTEST FAIL [differential pre-existing]: pre-existing finding must not fail the run, got exit {code}')
            ok = False
        else:
            print("SELFTEST OK [differential pre-existing]: 'pre-existing' found, run did not fail on it")

    # 9. differential: a defect present only at head is introduced and DOES
    # fail the run.
    with tempfile.TemporaryDirectory(prefix='localegate-diffintro-') as root:
        _build_clean_tree(root)
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: clean tree')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head: PR removes a basename the base still had.
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2].startswith('basename_parity') and r[1] == 'pt-PT'
                   and 'greet.dialog' in r[4]]
        if not matches or matches[0][3] != 'introduced':
            print(f'SELFTEST FAIL [differential introduced]: expected an introduced row, got {matches}')
            ok = False
        elif code == 0:
            print('SELFTEST FAIL [differential introduced]: introduced finding must fail the run, got exit 0')
            ok = False
        else:
            print("SELFTEST OK [differential introduced]: 'introduced' found, run failed")

    # 10. differential identity, not count: a tree that fixes one base defect
    # while introducing a different one must report one fixed AND one
    # introduced, and FAIL -- a count-only diff would net these to zero.
    with tempfile.TemporaryDirectory(prefix='localegate-diffidentity-') as root:
        _build_clean_tree(root)
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: pt-PT missing greet.dialog')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head: fix greet.dialog, but drop greeting.voc instead.
        _write(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'), 'ola pessoal\n')
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greeting.voc'))
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        parity_rows = [r for r in rows if r[2].startswith('basename_parity') and r[1] == 'pt-PT']
        fixed = [r for r in parity_rows if r[3] == 'fixed' and 'greet.dialog' in r[4]]
        introduced = [r for r in parity_rows if r[3] == 'introduced' and 'greeting.voc' in r[4]]
        if code == 0:
            print('SELFTEST FAIL [differential identity]: net-zero-by-count would report exit 0, got 0')
            ok = False
        elif not fixed:
            print(f'SELFTEST FAIL [differential identity]: expected a fixed greet.dialog row, got {parity_rows}')
            ok = False
        elif not introduced:
            print(f'SELFTEST FAIL [differential identity]: expected an introduced greeting.voc row, got {parity_rows}')
            ok = False
        else:
            print('SELFTEST OK [differential identity]: one fixed and one introduced, comparing by identity not count, run failed')

    # 11. avoidability: a new locale file whose non-compliant basename
    # matches a basename en-US already carries -- the locale had no lawful
    # alternative, so it is 'introduced, forced' and must NOT fail the run.
    with tempfile.TemporaryDirectory(prefix='localegate-forced-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'BadName.dialog'), 'has a capital\n')
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: en-US carries BadName.dialog')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head: pt-PT mirrors the same bad basename for the first time.
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadName.dialog'), 'tem uma maiuscula\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                   and os.path.basename(r[0]) == 'BadName.dialog']
        if not matches or matches[0][3] != 'introduced, forced':
            print(f'SELFTEST FAIL [avoidability forced]: expected "introduced, forced", got {matches}')
            ok = False
        elif code != 0:
            print(f'SELFTEST FAIL [avoidability forced]: forced finding must not fail the run, got exit {code}')
            ok = False
        else:
            print('SELFTEST OK [avoidability forced]: "introduced, forced" found, run did not fail')

    # 12. avoidability: a new locale file with a non-compliant basename that
    # en-US does not have -- the locale had a lawful alternative and chose a
    # bad name anyway, so it is 'introduced, avoidable' and DOES fail.
    with tempfile.TemporaryDirectory(prefix='localegate-avoidable-') as root:
        _build_clean_tree(root)
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: clean tree')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadOnly.dialog'), 'so aqui\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                   and os.path.basename(r[0]) == 'BadOnly.dialog']
        if not matches or matches[0][3] != 'introduced, avoidable':
            print(f'SELFTEST FAIL [avoidability avoidable]: expected "introduced, avoidable", got {matches}')
            ok = False
        elif code == 0:
            print('SELFTEST FAIL [avoidability avoidable]: avoidable finding must fail the run, got exit 0')
            ok = False
        else:
            print('SELFTEST OK [avoidability avoidable]: "introduced, avoidable" found, run failed')

    # 13. one forced and one avoidable finding in the same tree: both must
    # appear, in their own groups -- proving one does not mask the other.
    with tempfile.TemporaryDirectory(prefix='localegate-mixed-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'BadName.dialog'), 'has a capital\n')
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: en-US carries BadName.dialog')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadName.dialog'), 'tem uma maiuscula\n')
        _write(os.path.join(root, 'locale', 'pt-PT', 'BadOnly.dialog'), 'so aqui\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        forced_rows = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                       and os.path.basename(r[0]) == 'BadName.dialog' and r[3] == 'introduced, forced']
        avoidable_rows = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'pt-PT'
                           and os.path.basename(r[0]) == 'BadOnly.dialog' and r[3] == 'introduced, avoidable']
        if code == 0:
            print('SELFTEST FAIL [mixed forced+avoidable]: expected non-zero exit, got 0')
            ok = False
        elif not forced_rows:
            print(f'SELFTEST FAIL [mixed forced+avoidable]: expected an "introduced, forced" BadName.dialog row, got {rows}')
            ok = False
        elif not avoidable_rows:
            print(f'SELFTEST FAIL [mixed forced+avoidable]: expected an "introduced, avoidable" BadOnly.dialog row, got {rows}')
            ok = False
        else:
            print('SELFTEST OK [mixed forced+avoidable]: both groups present, one does not mask the other')

    # 14. differential across a relocated base checkout: the base worktree
    # for --base always lands at a fresh, unpredictable path (a new
    # tempfile.mkdtemp() per run), so a defect present at both refs must
    # still read as pre-existing even though the path it was found under at
    # base differs from the path it was found under at head. A key or
    # display built from the absolute on-disk path degrades this to
    # "everything at head is introduced" -- the exact bug this pins.
    with tempfile.TemporaryDirectory(prefix='localegate-relocated-') as root:
        _build_clean_tree(root)
        os.remove(os.path.join(root, 'locale', 'pt-PT', 'greet.dialog'))
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: pt-PT missing greet.dialog')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head == base here: nothing changed since the base commit, but the
        # --base worktree this run materializes is, by construction, at a
        # brand-new tempfile.mkdtemp() path distinct from `root` and from
        # every other run's worktree.
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2].startswith('basename_parity') and r[1] == 'pt-PT'
                   and 'greet.dialog' in r[4]]
        abs_paths = [r for r in rows if os.path.isabs(r[0])]
        if not matches or matches[0][3] != 'pre-existing':
            print(f'SELFTEST FAIL [relocated base checkout]: expected a pre-existing row, got {matches}')
            ok = False
        elif code != 0:
            print(f'SELFTEST FAIL [relocated base checkout]: pre-existing finding must not fail the run, got exit {code}')
            ok = False
        elif abs_paths:
            print(f'SELFTEST FAIL [relocated base checkout]: absolute path leaked into a row: {abs_paths}')
            ok = False
        else:
            print("SELFTEST OK [relocated base checkout]: 'pre-existing' found across differing base/head "
                  "checkout paths, run did not fail, no absolute path printed")

    # 15. slot_survival false positive pin: a locale template file with MORE
    # lines than en-US, but using the exact same slot SET, must report no
    # finding and must not fail the run. A locale is allowed more phrasings
    # than en-US; only the slot count would differ, never the slot set.
    with tempfile.TemporaryDirectory(prefix='localegate-slotcount-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'),
               'ola {name}\nopa {name}\nolarico meu {name}\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [])
        bad = [r for r in rows if r[2] == 'slot_survival' and r[1] == 'pt-PT' and r[3] == 'FAIL']
        if code != 0:
            print(f'SELFTEST FAIL [slot_survival same set, more lines]: expected clean pass, got exit {code}')
            ok = False
        elif bad:
            print(f'SELFTEST FAIL [slot_survival same set, more lines]: expected no finding, got {bad}')
            ok = False
        else:
            print('SELFTEST OK [slot_survival same set, more lines]: no finding, run did not fail')

    # 16. slot_survival dropped slot: the locale drops a slot en-US declares
    # -- a value the skill supplies is never spoken or captured.
    with tempfile.TemporaryDirectory(prefix='localegate-slotdrop-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'), 'ola\n')
        expect_fail('slot_survival dropped slot', root, "drops slot(s) en-US declares: ['name']")

    # 17. slot_survival extra slot: the locale uses a slot en-US does not
    # declare -- the locale expects a value nothing fills.
    with tempfile.TemporaryDirectory(prefix='localegate-slotextra-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'pt-PT', 'hello.intent'), 'ola {name} {extra}\n')
        expect_fail('slot_survival extra slot', root, "uses slot(s) en-US does not declare: ['extra']")

    # 18. base_name_compliance pairing: a '.blacklist' whose base name matches
    # a same-locale '.intent' is forced by that pairing (OVOS-INTENT-2 SS4.3)
    # and must NOT fail the run, even in en-US where the en-US-mirror
    # heuristic never applies.
    with tempfile.TemporaryDirectory(prefix='localegate-pairforced-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'Foo.intent'), 'foo {name}\n')
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: Foo.intent, no blacklist')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head: introduce Foo.blacklist, paired by base name with Foo.intent
        # in the same locale (OVOS-INTENT-2 SS4.3) -- forced even in en-US,
        # where the en-US-mirror heuristic never applies.
        _write(os.path.join(root, 'locale', 'en-US', 'Foo.blacklist'), 'bar\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [], base_ref=base_ref)
        matches = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'en-US'
                   and os.path.basename(r[0]) == 'Foo.blacklist']
        if code != 0:
            print(f'SELFTEST FAIL [pairing forced]: forced finding must not fail the run, got exit {code}')
            ok = False
        elif not matches or matches[0][3] != 'introduced, forced' or 'Foo.intent' not in matches[0][4]:
            print(f'SELFTEST FAIL [pairing forced]: expected "introduced, forced" naming Foo.intent, got {matches}')
            ok = False
        else:
            print(f'SELFTEST OK [pairing forced]: {matches[0][3]!r} with {matches[0][4]!r} found, run did not fail')

    # 19. base_name_compliance pairing: a '.blacklist' with NO same-locale
    # '.intent' of the same base name is not forced by anything -- avoidable,
    # and the run DOES fail.
    with tempfile.TemporaryDirectory(prefix='localegate-nopair-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'Bar.blacklist'), 'baz\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [])
        matches = [r for r in rows if r[2] == 'base_name_compliance' and r[1] == 'en-US'
                   and os.path.basename(r[0]) == 'Bar.blacklist']
        if code == 0:
            print('SELFTEST FAIL [pairing avoidable]: expected non-zero exit, got 0')
            ok = False
        elif not matches or matches[0][3] != 'FAIL':
            print(f'SELFTEST FAIL [pairing avoidable]: expected a FAIL row, got {matches}')
            ok = False
        else:
            print(f'SELFTEST OK [pairing avoidable]: {matches[0][4]!r} found, run failed')

    # 20. dialog_completeness: a dialog the skill speaks exists in en-US but
    # is missing from a locale that did not exist at base -- introduced,
    # names the locale and the dialog, and fails the run.
    with tempfile.TemporaryDirectory(prefix='localegate-dialogmissing-') as root:
        _build_clean_tree(root)
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: skill does not speak confirm_ready')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        _write(os.path.join(root, 'locale', 'en-US', 'confirm_ready.dialog'), 'ready to go\n')
        _write(os.path.join(root, '__init__.py'),
               'from ovos_workshop.skills import OVOSSkill\n'
               'class S(OVOSSkill):\n'
               '    @intent_handler("hello.intent")\n'
               '    def h(self, m):\n'
               '        self.speak_dialog("greet")\n'
               '        self.speak_dialog("confirm_ready")\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2] == 'dialog_completeness' and r[1] == 'pt-PT'
                   and 'confirm_ready.dialog' in r[4]]
        if code == 0:
            print('SELFTEST FAIL [dialog_completeness introduced]: expected non-zero exit, got 0')
            ok = False
        elif not matches or matches[0][3] != 'introduced':
            print(f'SELFTEST FAIL [dialog_completeness introduced]: expected an introduced row, got {matches}')
            ok = False
        elif 'pt-PT' not in matches[0][4]:
            print(f'SELFTEST FAIL [dialog_completeness introduced]: message must name the locale, got {matches[0][4]!r}')
            ok = False
        else:
            print(f'SELFTEST OK [dialog_completeness introduced]: {matches[0][4]!r} found, run failed')

    # 21. dialog_completeness: the same dialog missing in the same locale at
    # both base and head is pre-existing and must not fail the run -- the
    # skill's own defect, not this change's to fix.
    with tempfile.TemporaryDirectory(prefix='localegate-dialogpre-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'confirm_ready.dialog'), 'ready to go\n')
        _write(os.path.join(root, '__init__.py'),
               'from ovos_workshop.skills import OVOSSkill\n'
               'class S(OVOSSkill):\n'
               '    @intent_handler("hello.intent")\n'
               '    def h(self, m):\n'
               '        self.speak_dialog("greet")\n'
               '        self.speak_dialog("confirm_ready")\n')
        _git(root, 'init', '--quiet')
        _git_commit_all(root, 'base: confirm_ready already missing from pt-PT')
        base_ref = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
        # head == base: nothing changed since the base commit.
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, ['pt-PT'], [], base_ref=base_ref)
        matches = [r for r in rows if r[2] == 'dialog_completeness' and r[1] == 'pt-PT'
                   and 'confirm_ready.dialog' in r[4]]
        if not matches or matches[0][3] != 'pre-existing':
            print(f'SELFTEST FAIL [dialog_completeness pre-existing]: expected a pre-existing row, got {matches}')
            ok = False
        elif code != 0:
            print(f'SELFTEST FAIL [dialog_completeness pre-existing]: pre-existing finding must not fail the run, got exit {code}')
            ok = False
        else:
            print("SELFTEST OK [dialog_completeness pre-existing]: 'pre-existing' found, run did not fail")

    # 22. dialog_completeness: a dialog the skill speaks exists in every
    # locale -- no finding.
    with tempfile.TemporaryDirectory(prefix='localegate-dialogok-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, 'locale', 'en-US', 'confirm_ready.dialog'), 'ready to go\n')
        _write(os.path.join(root, 'locale', 'pt-PT', 'confirm_ready.dialog'), 'pronto\n')
        _write(os.path.join(root, '__init__.py'),
               'from ovos_workshop.skills import OVOSSkill\n'
               'class S(OVOSSkill):\n'
               '    @intent_handler("hello.intent")\n'
               '    def h(self, m):\n'
               '        self.speak_dialog("greet")\n'
               '        self.speak_dialog("confirm_ready")\n')
        rows, files_in, files_reported = [], 0, 0
        code = run_gate(root, [], [])
        bad = [r for r in rows if r[2] == 'dialog_completeness' and r[3] == 'FAIL']
        if code != 0:
            print(f'SELFTEST FAIL [dialog_completeness clean]: expected clean pass, got exit {code}')
            ok = False
        elif bad:
            print(f'SELFTEST FAIL [dialog_completeness clean]: expected no finding, got {bad}')
            ok = False
        else:
            print('SELFTEST OK [dialog_completeness clean]: no finding, run did not fail')

    # 23. dialog_completeness: a non-literal speak_dialog argument (a name
    # assembled at runtime, as ovos-skill-weather does) must DEGRADE the
    # check rather than invent a per-dialog finding, and must not fail.
    with tempfile.TemporaryDirectory(prefix='localegate-dialogdegraded-') as root:
        _build_clean_tree(root)
        _write(os.path.join(root, '__init__.py'),
               'from ovos_workshop.skills import OVOSSkill\n'
               'class S(OVOSSkill):\n'
               '    @intent_handler("hello.intent")\n'
               '    def h(self, m):\n'
               '        dialog = self.pick()\n'
               '        self.speak_dialog(dialog.name)\n')
        rows, files_in, files_reported = [], 0, 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run_gate(root, [], [])
        output = buf.getvalue()
        dc_rows = [r for r in rows if r[2].startswith('dialog_completeness')]
        if code != 0:
            print(f'SELFTEST FAIL [dialog_completeness degraded]: expected run not to fail, got exit {code}')
            ok = False
        elif dc_rows:
            print(f'SELFTEST FAIL [dialog_completeness degraded]: expected no per-dialog findings, got {dc_rows}')
            ok = False
        elif 'check dialog_completeness: RAN, DEGRADED' not in output:
            print(f'SELFTEST FAIL [dialog_completeness degraded]: expected a DEGRADED check line, got: {output}')
            ok = False
        else:
            print('SELFTEST OK [dialog_completeness degraded]: DEGRADED, no findings invented, run did not fail')

    # 12. package layout: a skill that keeps its locale in its package
    # (<repo>/<package>/locale) is invisible to a run at the repository root,
    # which reads nothing and passes. find_skill_paths() must find the package,
    # and the gate run there must fail on a violation. This pins the #113
    # canary defect: the policy job ran on '.' and passed every locale change.
    with tempfile.TemporaryDirectory(prefix='localegate-package-') as repo:
        pkg = os.path.join(repo, 'my_skill')
        _build_clean_tree(pkg)
        _write(os.path.join(pkg, 'locale', 'pt-PT', 'only_here.dialog'), 'so aqui\n')
        _write(os.path.join(repo, '_gh_automations', 'fixture', 'locale', 'en-US', 'x.dialog'), 'x\n')
        _write(os.path.join(repo, '.hidden', 'locale', 'en-US', 'x.dialog'), 'x\n')
        _write(os.path.join(repo, 'docs', 'locale', 'README.md'), 'no locale files here\n')
        found = find_skill_paths(repo, '', ('_gh_automations',))
        narrowed_pkg = find_skill_paths(repo, 'my_skill', ('_gh_automations',))
        narrowed_loc = find_skill_paths(repo, 'my_skill/locale', ('_gh_automations',))
        rows, files_in, files_reported = [], 0, 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            root_code = run_gate(repo, [], [])
        root_out = buf.getvalue()
        if found != ['my_skill']:
            print(f"SELFTEST FAIL [package layout find]: expected ['my_skill'], got {found}")
            ok = False
        elif narrowed_pkg != ['my_skill'] or narrowed_loc != ['my_skill']:
            print(f'SELFTEST FAIL [package layout locale_paths]: expected my_skill for both, got {narrowed_pkg} {narrowed_loc}')
            ok = False
        elif not (root_code == 0 and '0 in, 0 out' in root_out):
            print(f'SELFTEST FAIL [package layout root]: expected the repository-root run to read nothing, got exit {root_code}')
            ok = False
        else:
            print("SELFTEST OK [package layout]: found ['my_skill'] (hidden, excluded and file-less locale dirs skipped), "
                  "locale_paths honoured, a root run reads 0 in, 0 out")
            expect_fail('package layout gate', os.path.join(repo, found[0]), 'only_here.dialog')

    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('skill_path', nargs='?')
    ap.add_argument('--locale', action='append', default=[])
    ap.add_argument('--md', action='append', default=[], help='.md file(s) to run the prose lint over')
    ap.add_argument('--base', default=None, help='git ref to diff against; findings become introduced/pre-existing/fixed')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--find-skills', metavar='ROOT', default=None,
                    help='print, one per line, the skill paths under ROOT that hold a locale/ directory, and exit')
    ap.add_argument('--locale-paths', default='',
                    help='with --find-skills: space-separated paths to search instead of all of ROOT')
    ap.add_argument('--exclude', action='append', default=[],
                    help='with --find-skills: a directory name to skip (repeatable)')
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if args.find_skills is not None:
        for p in find_skill_paths(args.find_skills, args.locale_paths, tuple(args.exclude)):
            print(p)
        sys.exit(0)

    if not args.skill_path:
        ap.error('skill checkout path is required unless --selftest')

    sys.exit(run_gate(args.skill_path, args.locale, args.md, base_ref=args.base))


if __name__ == '__main__':
    main()
