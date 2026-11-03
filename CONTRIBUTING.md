# Contributing to Dia

Thanks for helping with Dia! Please read this before opening a pull request.

## Licensing and the CLA

Dia is released under the [PolyForm Noncommercial License 1.0.0](LICENSE) and
is also offered under a separate [commercial license](COMMERCIAL-LICENSE.md) by
the project owner. To make that possible, every contribution needs a Contributor License Agreement (CLA).

By submitting a contribution (pull request, patch, or any other form) you agree
that:

1. **You wrote it** (or have the right to submit it) and it does not knowingly
   infringe anyone else's rights. If your employer has rights to your work, you
   have their permission to contribute it.
2. **You keep your copyright.** You are not transferring ownership.
3. **You grant the project owner (Dawid Solarewicz, "Solar9") a perpetual,
   worldwide, non-exclusive, royalty-free, irrevocable license** to use,
   reproduce, modify, sublicense, distribute and relicense your contribution
   under any terms, including the PolyForm Noncommercial License and
   proprietary/commercial licenses.
4. **You grant recipients of Dia a patent license** covering your contribution
   to the extent it is needed to use Dia, and it is provided "as is", without
   warranty.

Sign by adding this line to your pull request description (once; it covers
later contributions too):

```
I have read CONTRIBUTING.md and agree to the Contributor License Agreement.
```

Pull requests without this statement will not be merged.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
```

CI also runs `lint-imports` (layer rules) and `mypy` (strict for `dia.core`):

```bash
lint-imports && mypy
```

## Where new code goes

One module, one job. The module map and layer rules are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#module-map); in short:

| You are adding... | Put it in |
|---|---|
| a CLI command | `src/dia/cli/<group>.py`: handler + a `COMMANDS` entry, and the name in `ORDER` in `cli/__init__.py` (the order of `dia --help`) |
| an HTTP endpoint | the matching module in `src/dia/channels/api/` (add it to its `routes(ch)`) |
| something the orchestrator does for every interface | a collaborator in `src/dia/core/` plus a one-line delegate on `Orchestrator` (keep `orchestrator.py` small) |
| a quality check, a project-health report | `src/dia/quality/` |
| something Dia remembers or learns | `src/dia/knowledge/` |
| goals, missions, schedules, watchers | `src/dia/work/` |
| desktop integration (window, tray, services, devices) | `src/dia/desktop/` |
| builds, updates, game analysis | `src/dia/release/` |
| a new agent, brain, forge, toolchain, skill, channel... | a plugin: its own package or one of the plugin packages, registered through an entry point (never a special case in the core) |
| a UI view or component | `src/dia/ui/static/js/views/` or `js/ui/` (and add the file to the service worker's `SHELL` list) |

Rules of thumb: `dia.core` must not import `channels`, `cli`, `desktop` or `ui`
(`lint-imports` fails otherwise); keep imports of optional extras inside the
functions that need them; write JSON state with `dia.core.jsonfile`; change the
SQLite schema by appending a migration to `dia.core.store.MIGRATIONS`.
If a refactor moves code, move it in one commit and change it in the next.

Optional: `pip install pre-commit && pre-commit install` runs the same ruff
checks before each commit (DIA-03). Please make sure tests and lint pass before
opening a pull request. Prefer PRs into `main` rather than pushing straight to it.
