"""CI must reject incomplete signing credentials before publishing a release."""

import base64
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "mobile/scripts/prepare-release-signing.sh"
SECRETS = ("KEYSTORE_BASE64", "DIA_KEYSTORE_PASSWORD", "DIA_KEY_ALIAS", "DIA_KEY_PASSWORD")
pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="Bash is required")


def prepare(tmp_path, values):
    env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_ENV=str(tmp_path / "github-env"), **values)
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)


def credentials():
    return {
        "KEYSTORE_BASE64": base64.b64encode(b"test-keystore").decode(),
        "DIA_KEYSTORE_PASSWORD": "secret",
        "DIA_KEY_ALIAS": "dia",
        "DIA_KEY_PASSWORD": "secret",
    }


@pytest.mark.parametrize("missing", SECRETS)
def test_missing_signing_secret_cannot_enable_release_signing(tmp_path, missing):
    values = credentials()
    del values[missing]
    result = prepare(tmp_path, values)
    assert result.returncode != 0
    assert missing in result.stdout
    assert not (tmp_path / "github-env").exists()
    assert not (tmp_path / "dia.jks").exists()


def test_invalid_base64_cannot_enable_release_signing(tmp_path):
    result = prepare(tmp_path, {**credentials(), "KEYSTORE_BASE64": "not-base64!"})
    assert result.returncode != 0
    assert not (tmp_path / "github-env").exists()


def test_valid_credentials_prepare_private_keystore_without_logging_secrets(tmp_path):
    result = prepare(tmp_path, credentials())
    assert result.returncode == 0, result.stderr
    keystore = tmp_path / "dia.jks"
    assert keystore.read_bytes() == b"test-keystore"
    assert stat.S_IMODE(keystore.stat().st_mode) == 0o600
    assert (tmp_path / "github-env").read_text() == f"DIA_KEYSTORE_FILE={keystore}\n"
    assert "secret" not in result.stdout + result.stderr
