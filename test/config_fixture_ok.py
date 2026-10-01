"""Fixture module for the config entry-point checks in test_scripts.py.

A config entry point names data: a dict, or a callable that returns one.
"""

CONFIG = {"en-US": {"voice": "beep"}}

NOT_A_DICT = "i am a string"


def make_config():
    return {"en-US": {"voice": "boop"}}
