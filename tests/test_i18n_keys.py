"""
Regression test: every i18n key referenced in source code must be defined
in both the EN and ZH message dictionaries.
"""

import re
from pathlib import Path

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
