from pathlib import Path

import pytest

from dia.ui import theme


def test_system_is_a_choice_for_the_app_and_the_phone_not_the_widget(tmp_path: Path) -> None:
    assert theme.valid("name", "system") and theme.valid("phone", "system")
    assert not theme.valid("widget", "system")  # Plasma draws it: no prefers-color-scheme there
    assert theme.valid("widget", "light") and not theme.valid("name", "no-such-theme")
    assert not theme.valid("name", None) and not theme.valid("name", 5)

    chosen = theme.update(tmp_path, {"name": "system", "phone": "system"})
    assert chosen == {"name": "system", "phone": "system", "widget": None}
    assert theme.current(tmp_path) == "system" and theme.current(tmp_path, "phone") == "system"
    assert theme.current(tmp_path, "widget") == "system"  # follows the app

    with pytest.raises(ValueError, match="widget"):
        theme.update(tmp_path, {"widget": "system"})
    with pytest.raises(ValueError, match="no theme"):
        theme.update(tmp_path, {"name": "nonsense"})
    # a widget that was set before is kept when the app moves to "system"
    theme.update(tmp_path, {"widget": "midnight"})
    assert theme.settings(tmp_path)["widget"] == "midnight"


def test_a_saved_system_theme_is_read_back(tmp_path: Path) -> None:
    (tmp_path / "ui-theme.json").write_text('{"name": "system", "widget": "system"}')
    assert theme.settings(tmp_path) == {"name": "system", "phone": None, "widget": None}


def test_the_server_resolves_system_to_a_theme_file() -> None:
    assert theme.concrete("system") == "dark" and theme.concrete("system", dark=False) == "light"
    assert theme.concrete("midnight") == "midnight"
    assert theme.variables("system")["bg"] == theme.variables("dark")["bg"]
    assert theme.variables("system", dark=False)["bg"] == theme.variables("light")["bg"]
    assert theme.colors("system", dark=False)["bg"] == theme.colors("light")["bg"]
