from dia import __version__
from dia.about import GITHUB, WEBSITE, components, identity, snapshot


def test_identity_points_at_solar() -> None:
    info = identity()
    assert info["name"] == "Dia" and info["version"] == __version__
    assert info["author"] == "Solar"
    assert info["website"] == WEBSITE == "https://solar9.me"
    assert info["github"] == GITHUB == "https://github.com/Solar9/Dia"
    assert info["email"] == "solar@solar9.me"
    assert "PolyForm" in info["license"]


def test_snapshot_always_lists_dia_and_python() -> None:
    info = snapshot()
    names = [row["name"] for row in info["components"]]
    assert names[:2] == ["Dia", "Python"]
    assert info["components"][0]["version"] == __version__
    assert "config" not in info
    dia, python, *rest = components()
    assert dia["name"] == "Dia" and python["name"] == "Python"
    assert all("name" in row and "version" in row for row in rest)
