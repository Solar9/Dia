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

Optional: `pip install pre-commit && pre-commit install` runs the same ruff
checks before each commit (DIA-03). Please make sure tests and lint pass before
opening a pull request. Prefer PRs into `main` rather than pushing straight to it.
