import json

import pytest

from dia.desktop import appwindow, offline
from dia.ui import theme


@pytest.mark.parametrize(
    ("unit", "state"),
    [
        (None, "starting"),
        ({}, "starting"),
        ({"state": "activating"}, "starting"),
        ({"state": "active"}, "starting"),  # the unit runs but the API does not answer yet
        ({"state": "inactive"}, "stopped"),
        ({"state": "deactivating"}, "stopped"),
        ({"state": "failed"}, "error"),
        ({"state": "missing"}, "missing"),
        ({"state": "something-new"}, "stopped"),
    ],
)
def test_offline_state_follows_the_unit(unit, state):
    assert offline.offline_state(unit) == state


def test_every_language_says_every_state():
    english = offline.WORDS["en"]
    assert set(offline.WORDS) == {"en", "pl", "de", "fr", "es", "it", "pt"}
    for language, words in offline.WORDS.items():
        assert set(words) == set(english), language
        for state in offline.STATES:
            title, text = words[state]
            assert title and text, (language, state)


@pytest.mark.parametrize("language", sorted(offline.WORDS))
@pytest.mark.parametrize("frameless", [True, False])
def test_page_renders_without_leftovers(language, frameless):
    page = appwindow.offline_page(language, frameless)
    assert "__" not in page
    words = json.loads(page.split("const WORDS = ")[1].split(";\n")[0])
    expected = {
        k: list(v) if isinstance(v, tuple) else v for k, v in offline.WORDS[language].items()
    }
    assert words == expected
    assert ("data-edge=" in page) is frameless
    assert 'data-state="starting"' in page


def test_page_opens_in_the_given_state_and_can_switch():
    page = appwindow.offline_page("en", True, state="error")
    assert 'data-state="error"' in page and 'diaOfflineState("error")' in page
    assert "window.diaOfflineState = (state)" in page  # the window pushes changes into it
    assert 'data-state="starting"' in appwindow.offline_page("en", True, state="nonsense")
    assert "dia-window:show-logs" in page and "dia-window:start-services" in page


def test_page_uses_the_current_theme():
    light = theme.variables("light")
    page = appwindow.offline_page("en", True, variables=light)
    assert f"--bg:{light['bg']};" in page and f"--accent:{light['accent']};" in page
    dark = appwindow.offline_page("en", True)
    assert f"--bg:{theme.variables('dark')['bg']};" in dark
    assert f"--bg:{light['bg']};" not in dark or light["bg"] == theme.variables("dark")["bg"]


def test_theme_values_cannot_inject_markup():
    css = offline.theme_css({"bg": "red;}</style><script>alert(1)</script>", "text": "url(x)"})
    assert "<" not in css and "url(" not in css and "script" not in css
    assert "--bg:#131317;" in css  # fell back to the default


def test_window_bridge_knows_the_logs_button():
    assert appwindow.window_command("dia-window:show-logs") == ("show-logs", [])
    assert appwindow.window_command("dia-window:start-services") == ("start-services", [])
