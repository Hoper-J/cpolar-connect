"""
Regression test: every i18n key referenced in source code must be defined
in both the EN and ZH message dictionaries.
"""

import ast
import re
from pathlib import Path

import pytest

import cpolar_connect
from cpolar_connect.i18n import Messages

KEY_PATTERN = re.compile(r"""\b_\(\s*['"]([a-z0-9_.]+)['"]""")


def _used_keys():
    src_dir = Path(cpolar_connect.__file__).parent
    keys = set()
    for py_file in src_dir.glob("*.py"):
        keys.update(KEY_PATTERN.findall(py_file.read_text(encoding="utf-8")))
    return keys


def test_all_used_keys_defined_in_english():
    missing = sorted(k for k in _used_keys() if k not in Messages.EN)
    assert not missing, f"i18n keys missing in EN: {missing}"


def test_all_used_keys_defined_in_chinese():
    missing = sorted(k for k in _used_keys() if k not in Messages.ZH)
    assert not missing, f"i18n keys missing in ZH: {missing}"


def test_en_and_zh_define_the_same_keys():
    assert sorted(Messages.EN) == sorted(Messages.ZH)


PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _placeholders(message):
    return set(PLACEHOLDER.findall(message))


def test_en_and_zh_messages_take_the_same_placeholders():
    different = {
        key: (_placeholders(Messages.EN[key]), _placeholders(Messages.ZH[key]))
        for key in Messages.EN
        if _placeholders(Messages.EN[key]) != _placeholders(Messages.ZH[key])
    }
    assert not different


def _calls_with_a_literal_key():
    """(file, line, key, keyword names) of every `_("some.key", ...)` call."""
    src_dir = Path(cpolar_connect.__file__).parent
    for py_file in sorted(src_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            names = {keyword.arg for keyword in node.keywords}
            if None in names:  # **kwargs: cannot be checked here
                continue
            yield py_file.name, node.lineno, node.args[0].value, names


def test_every_call_supplies_the_placeholders_of_its_message():
    """A missing one is not an exception at runtime: the user gets the raw
    message with "[Format error: ...]" appended."""
    missing = [
        f"{name}:{line} {key}: {sorted(_placeholders(Messages.EN[key]) - given)}"
        for name, line, key, given in _calls_with_a_literal_key()
        if key in Messages.EN and _placeholders(Messages.EN[key]) - given
    ]
    assert not missing, "\n".join(missing)


# Before the first `init` there is no account to name
COMMANDS_WITHOUT_ACCOUNT = {"info.no_accounts"}


@pytest.mark.parametrize("messages", [Messages.EN, Messages.ZH], ids=["en", "zh"])
def test_commands_in_messages_name_the_account(messages):
    """Printed as it stands, a command acts on the current account, which
    need not be the one the message is about (`-a`, CPOLAR_ACCOUNT)."""
    command = re.compile(r"cpolar-connect(?! -a \{account\})")
    offending = sorted(
        key
        for key, text in messages.items()
        if command.search(text) and key not in COMMANDS_WITHOUT_ACCOUNT
    )
    assert not offending
