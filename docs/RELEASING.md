# Releasing Dia

Private work lives in **Solar9/Dia_DEV**. Public installs and updates come from
**Solar9/Dia** (wheels, installers, PKGBUILD, SHA256SUMS).

## Rules (DIA-02)

1. **Publish only from a commit with green CI.** Pushing a release tag
   (`v0.1.1`, …) runs `publish.yml`, which first runs the same checks as CI
   (ruff, pytest on Python 3.11 / 3.13 / 3.14, and the Qt job) on that commit
   and only then copies the tree to Solar9/Dia. A failed check aborts publish.
2. **Never move a published tag.** If 0.1.1 is wrong, ship **0.1.2**. Moving
   `v0.1.0` after people already downloaded it leaves two different “0.1.0”
   builds in the wild.
3. **One version everywhere.** `pyproject.toml` is the source of truth. Before
   tagging:

   ```sh
   scripts/bump-version 0.1.1
   scripts/bump-version --check   # also run by tests and publish-release.sh
   ```

   That updates `__init__.py`, the Plasma widget, mobile npm / Android / iOS.
   `packaging/arch/PKGBUILD` keeps `@VERSION@` until the public release job
   fills it in.

## Steps for 0.1.x

1. Land the work on `main` through a PR with green CI (preferred; see DIA-03).
2. `scripts/bump-version X.Y.Z` and a CHANGELOG section `## [X.Y.Z]`.
3. Tag `vX.Y.Z` on that commit and push the tag to Dia_DEV.
4. Wait for Publish + the public Release workflow. Confirm the GitHub release
   on Solar9/Dia has the wheel, `install.sh` / `install.ps1`, PKGBUILD and
   SHA256SUMS.
5. Smoke-test on a clean machine (`docs/test-reports`): install and tray
   update, as in DIA-01 / DIA-47.

Private `v0.0.*` tags are ignored by publish (old pre-reset builds).
