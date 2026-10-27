"""Tidying a folder (Downloads by default): Dia proposes, you approve, it can undo.

"Dia, posprzątaj pobrane" shows what would move where (images to Obrazy/,
installers to Instalatory/, files untouched for a month to Archiwum/<month>/)
and moves nothing until you say yes. Then it moves, never deletes and never
overwrites (a name that is taken gets a number), and keeps a record so
"cofnij porządki" (``dia tidy --undo``) puts everything back.

    [tidy]
    folders = ["~/Pobrane"]        # the folders Dia may tidy (default: Downloads)
    archive_days = 30              # untouched this long: to the archive (0: never)
    # groups = { "Obrazy" = ["jpg", "png"], ... }   # your own folder names and types

Only files directly in the folder are moved; folders, hidden files and
downloads still in progress (.part, .crdownload) are left alone.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

GROUPS = {
    "Obrazy": ["jpg", "jpeg", "png", "gif", "webp", "svg", "heic", "bmp", "tiff"],
    "Dokumenty": [
        "pdf",
        "doc",
        "docx",
        "odt",
        "txt",
        "md",
        "rtf",
        "xls",
        "xlsx",
        "ods",
        "csv",
        "pptx",
        "odp",
        "epub",
    ],
    "Archiwa": ["zip", "tar", "gz", "tgz", "xz", "zst", "7z", "rar", "bz2"],
    "Instalatory": ["appimage", "deb", "rpm", "exe", "msi", "dmg", "flatpakref", "apk"],
    "Wideo": ["mp4", "mkv", "webm", "mov", "avi"],
    "Audio": ["mp3", "flac", "ogg", "wav", "m4a", "opus"],
    "Grafika 3D": ["blend", "fbx", "obj", "glb", "gltf"],
    "Fonty": ["ttf", "otf", "woff", "woff2"],
}
IN_PROGRESS = (".part", ".crdownload", ".download", ".tmp")


class TidyError(ValueError):
    pass


def downloads_dir() -> Path:
    try:
        out = subprocess.run(
            ["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if out and Path(out) != Path.home():
            return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    for name in ("Pobrane", "Downloads"):
        if (Path.home() / name).is_dir():
            return Path.home() / name
    return Path.home() / "Downloads"


def _suffix(path: Path) -> str:
    name = path.name.lower()
    for double in (".tar.gz", ".tar.xz", ".tar.zst", ".pkg.tar.zst"):
        if name.endswith(double):
            return "tar"
    return path.suffix.lower().lstrip(".")


class Tidy:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.options = dia.config.section("tidy")
        self.root = dia.config.data_dir / "tidy"

    def folders(self) -> list[Path]:
        configured = self.options.get("folders")
        found = [Path(os.path.expanduser(f)) for f in configured] if configured else []
        return [p.resolve() for p in found or [downloads_dir()]]

    def folder(self, name: str | None) -> Path:
        allowed = self.folders()
        if not name:
            return allowed[0]
        wanted = Path(os.path.expanduser(name)).resolve()
        if wanted not in allowed:
            names = ", ".join(str(p) for p in allowed)
            raise TidyError(f"{wanted} is not one of the folders Dia may tidy ({names})")
        return wanted

    def plan(self, folder: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        """What would move where; nothing moves until :meth:`apply`."""
        base = self.folder(folder)
        if not base.is_dir():
            raise TidyError(f"{base} does not exist")
        groups = self.options.get("groups") or GROUPS
        by_type = {ext: name for name, exts in groups.items() for ext in exts}
        days = int(self.options.get("archive_days", 30))
        cutoff = (now or datetime.now()) - timedelta(days=days)
        archive = self.options.get("archive_name", "Archiwum")
        moves = []
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.is_symlink() or path.name.startswith("."):
                continue
            if path.name.lower().endswith(IN_PROGRESS):
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            if days and modified < cutoff:
                target, reason = (
                    f"{archive}/{modified:%Y-%m}",
                    f"untouched since {modified:%Y-%m-%d}",
                )
            elif group := by_type.get(_suffix(path)):
                target, reason = group, _suffix(path)
            else:
                continue
            moves.append({"from": path.name, "to": f"{target}/{path.name}", "reason": reason})
        plan = {
            "id": secrets.token_hex(4),
            "folder": str(base),
            "moves": moves,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "proposed",
        }
        if moves:
            self._save(plan)
        return plan

    def _path(self, plan_id: str) -> Path:
        if not plan_id.isalnum():
            raise TidyError(f"no tidy plan {plan_id}")
        return self.root / f"{plan_id}.json"

    def _save(self, plan: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(plan["id"]).write_text(json.dumps(plan, indent=1, ensure_ascii=False))

    def load(self, plan_id: str) -> dict[str, Any]:
        try:
            return json.loads(self._path(plan_id).read_text())
        except OSError:
            raise TidyError(f"no tidy plan {plan_id}") from None

    def last(self, status: str = "applied") -> dict[str, Any] | None:
        plans = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in plans:
            plan = json.loads(path.read_text())
            if plan["status"] == status:
                return plan
        return None

    def apply(self, plan_id: str) -> dict[str, Any]:
        """Move the files; never deletes, never overwrites. Returns the plan with what moved."""
        plan = self.load(plan_id)
        if plan["status"] != "proposed":
            raise TidyError(f"tidy plan {plan_id} is {plan['status']}")
        base = self.folder(plan["folder"])
        done = []
        for move in plan["moves"]:
            source = base / move["from"]
            if not source.is_file():
                continue  # gone or changed since the preview
            target = _free(base / move["to"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            done.append({"from": move["from"], "to": str(target.relative_to(base))})
        plan.update(status="applied", moved=done)
        self._save(plan)
        self.dia.audit("tidy.apply", plan["folder"], f"{len(done)} files ({plan_id})")
        return plan

    def undo(self, plan_id: str | None = None) -> dict[str, Any]:
        plan = self.load(plan_id) if plan_id else self.last("applied")
        if not plan or plan["status"] != "applied":
            raise TidyError("nothing to undo")
        base = Path(plan["folder"])
        restored = 0
        for move in plan.get("moved", []):
            source, target = base / move["to"], _free(base / move["from"])
            if source.is_file():
                shutil.move(str(source), str(target))
                restored += 1
                try:
                    source.parent.rmdir()  # only when it is now empty
                except OSError:
                    pass
        plan.update(status="undone", restored=restored)
        self._save(plan)
        self.dia.audit("tidy.undo", plan["folder"], f"{restored} files ({plan['id']})")
        return plan


def _free(path: Path) -> Path:
    """``path``, or ``name (2).ext`` etc. when it is taken."""
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise TidyError(f"too many files named like {path.name}")


def files_pl(n: int) -> str:
    """ "1 plik", "3 pliki", "5 plików" (Polish plural forms)."""
    if n == 1:
        return "1 plik"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} pliki"
    return f"{n} plików"


def summary(plan: dict[str, Any], language: str) -> str:
    """The preview in a sentence or two (to say or show before asking)."""
    counts: dict[str, int] = {}
    for move in plan["moves"]:
        top = move["to"].split("/")[0]
        counts[top] = counts.get(top, 0) + 1
    parts = ", ".join(f"{n} → {name}/" for name, n in sorted(counts.items(), key=lambda c: -c[1]))
    pl = language == "pl"
    if not plan["moves"]:
        return (
            f"W {plan['folder']} nie ma czego porządkować." if pl else f"{plan['folder']} is tidy."
        )
    total = len(plan["moves"])
    return (
        f"Przeniosę {files_pl(total)} w {plan['folder']}: {parts}. Nic nie usuwam."
        if pl
        else f"I'd move {total} files in {plan['folder']}: {parts}. Nothing is deleted."
    )
