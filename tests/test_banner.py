from dia import banner
from dia.cli import main


def test_the_ring_is_drawn_from_the_icon() -> None:
    rows = banner.ring(8)
    assert len(rows) == 8
    middle = rows[4]
    assert "\033[38;2;" in middle  # coloured
    assert banner._pixel(0.5, 0.5) and banner._pixel(0.5, 0.05) and not banner._pixel(0.5, 0.2)
    assert banner._pixel(0.0, 0.0) is None  # the corners are transparent


def test_dia_version(capsys) -> None:
    assert main(["version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Dia ") and "\033[" not in out  # not a terminal: plain text
