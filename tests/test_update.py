import hashlib
import json

import pytest

from dia import update


def test_versions_compare_as_numbers_and_ignore_prereleases():
    assert update.newer("0.10.0", "0.9.9")
    assert update.newer("v1.0.0", "0.2.1")
    assert not update.newer("0.2.1", "0.2.1")
    assert not update.newer("0.3.0rc1", "0.2.1")
    assert not update.newer("main", "0.2.1")
    # After the version reset, old private 0.2.x must see 0.1.1 as an update (DIA-47).
    assert update.newer("0.1.1", "0.2.3")
    assert update.newer("0.1.1", "0.2.0")
    assert update.newer("0.1.1", "0.1.0")  # also true by ordinary compare
    assert not update.newer("0.1.0", "0.2.3")  # post-reset floor is 0.1.1
    assert not update.newer("0.1.1", "0.3.0")  # real future versions stay normal


def test_checksum_is_read_from_a_sha256sum_file():
    digest = "a" * 64
    sums = f"{'b' * 64}  other.txt\n{digest} *dia-1.0.0-py3-none-any.whl\n"
    assert update.checksum(sums, "dia-1.0.0-py3-none-any.whl") == digest
    with pytest.raises(ValueError):
        update.checksum(sums, "missing.whl")


def test_latest_reports_only_a_newer_release(monkeypatch):
    def release(tag):
        return json.dumps({"tag_name": tag, "html_url": "u", "body": "notes"}).encode()

    monkeypatch.setattr(update, "_get", lambda url: release("v99.0.0"))
    assert update.latest()["version"] == "99.0.0"
    monkeypatch.setattr(update, "_get", lambda url: release("v0.0.1"))
    assert update.latest() is None


def test_install_verifies_the_wheel_before_pip(monkeypatch):
    wheel = b"wheel bytes"
    name = "dia-99.0.0-py3-none-any.whl"
    sums = f"{hashlib.sha256(wheel).hexdigest()}  {name}\n".encode()
    ran = []
    monkeypatch.setattr(update, "editable", lambda: False)
    monkeypatch.setattr(update, "_get", lambda url: sums if url.endswith("SHA256SUMS") else wheel)
    monkeypatch.setattr(
        update.subprocess,
        "run",
        lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})(),
    )
    update.install("99.0.0")
    assert ran and ran[0][1:5] == ["-m", "pip", "install", "--quiet"]

    ran.clear()
    monkeypatch.setattr(update, "_get", lambda url: sums if url.endswith("SHA256SUMS") else b"x")
    with pytest.raises(RuntimeError, match="checksum"):
        update.install("99.0.0")
    assert not ran


def test_a_source_checkout_is_never_updated(monkeypatch):
    monkeypatch.setattr(update, "editable", lambda: True)
    with pytest.raises(RuntimeError, match="git"):
        update.install("99.0.0")


def test_a_pacman_install_is_never_pip_updated(monkeypatch):
    monkeypatch.setattr(update, "editable", lambda: False)
    monkeypatch.setattr(update, "system_package", lambda: True)
    with pytest.raises(RuntimeError, match="package manager"):
        update.install("99.0.0")
    assert "pacman" in update.package_update_hint()


def test_system_package_is_usr_outside_a_venv(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "editable", lambda: False)
    monkeypatch.setattr(update.sys, "prefix", "/usr")
    monkeypatch.setattr(update.sys, "base_prefix", "/usr")
    monkeypatch.setattr(update.dia, "__file__", "/usr/lib/python3.13/site-packages/dia/__init__.py")
    assert update.system_package()
    monkeypatch.setattr(update.sys, "prefix", str(tmp_path / "venv"))
    monkeypatch.setattr(update.sys, "base_prefix", "/usr")
    assert not update.system_package()
