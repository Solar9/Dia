import sys
from pathlib import Path

from dia import desktop


def test_shortcuts_with_the_icon(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(desktop, "desktop_dir", lambda: tmp_path / "Pulpit")
    icons = tmp_path / "data" / "icons" / "hicolor"
    for size, data in (("256", (desktop.ICONS / "dia-256.png").read_bytes()), ("48", b"other app")):
        (icons / f"{size}x{size}" / "apps").mkdir(parents=True)
        (icons / f"{size}x{size}" / "apps" / "dia.png").write_bytes(data)  # 0.2.0's / another's
    done = desktop.install(Path("/etc/dia.toml"), desktop=True, autostart=True)
    assert len(done) == 3
    menu = (tmp_path / "data" / "applications" / "dia.desktop").read_text()
    assert "Icon=io.github.solar9.dia\n" in menu and "Name=Dia" in menu
    assert "Categories=Utility;\n" in menu
    assert "Development" not in menu  # one main category only (DIA-27)
    assert f"Exec={sys.executable} -m dia --config /etc/dia.toml app" in menu
    assert (tmp_path / "Pulpit" / "dia.desktop").stat().st_mode & 0o111  # launchable
    autostart = (tmp_path / "config" / "autostart" / "dia.desktop").read_text()
    assert "app --background" in autostart
    assert (icons / "256x256" / "apps" / "io.github.solar9.dia.png").exists()
    assert not (icons / "256x256" / "apps" / "dia.png").exists()  # 0.2.0's copy, removed
    assert (icons / "48x48" / "apps" / "dia.png").read_bytes() == b"other app"  # not ours: kept
    assert (icons / "scalable" / "apps" / "io.github.solar9.dia.svg").exists()
    removed = desktop.uninstall()
    assert len(removed) == 3 and not (tmp_path / "Pulpit" / "dia.desktop").exists()
