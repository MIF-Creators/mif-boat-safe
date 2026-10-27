from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = REPO_ROOT / "system"

# Console scripts in pyproject.toml call main() from these files.
ENTRY_POINTS = [
    "system/vehicle/main.py",
    "system/navigation_server/main.py",
    "system/control_center/main.py",
]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_entry_point_has_main_function(entry_point):
    text = (REPO_ROOT / entry_point).read_text(encoding="utf-8")

    assert "\ndef main(" in text


def test_system_code_does_not_modify_sys_path():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in SYSTEM_DIR.rglob("*.py")
        if "sys.path" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
