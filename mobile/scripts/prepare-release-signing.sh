#!/usr/bin/env bash
# GitHub Actions: never turn a missing release key into an unsigned download.
set -euo pipefail

for name in KEYSTORE_BASE64 DIA_KEYSTORE_PASSWORD DIA_KEY_ALIAS DIA_KEY_PASSWORD; do
  if [[ -z "${!name:-}" ]]; then
    echo "::error::Missing Android signing secret: $name. Configure the DIA_ANDROID_* secrets documented in docs/MOBILE.md. Use the debug APK artifact for testing."
    exit 1
  fi
done

umask 077
printf '%s' "$KEYSTORE_BASE64" | base64 --decode > "$RUNNER_TEMP/dia.jks"
test -s "$RUNNER_TEMP/dia.jks"
echo "DIA_KEYSTORE_FILE=$RUNNER_TEMP/dia.jks" >> "$GITHUB_ENV"
