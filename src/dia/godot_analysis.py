"""A look at a Godot project's scenes, scripts and assets for likely
performance and structure problems: "Dia, przeanalizuj sceny nova".

Static and read-only: it parses the .tscn/.gd files and image headers, no
editor needed. It finds the usual suspects (very large or deep scenes, many
real-time lights or particle systems in one scene, node lookups inside
``_process``, huge textures, scripts doing per-frame work); ``--agent`` (or
"... i doradź") hands the findings to an agent that reads the code and
proposes what to fix first.

    [godot_analysis]
    max_nodes = 1000        # per scene
    max_depth = 12
    max_lights = 8
    max_texture = 4096      # pixels on the longer side
"""

from __future__ import annotations

import re
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

LIGHTS = re.compile(r'type="(OmniLight3D|SpotLight3D|DirectionalLight3D|PointLight2D)"')
PARTICLES = re.compile(r'type="(GPUParticles[23]D|CPUParticles[23]D)"')
NODE = re.compile(r'^\[node name="[^"]*"(?: type="([^"]*)")?(?: parent="([^"]*)")?', re.M)
LOOKUP = re.compile(
    r"\bget_node\s*\(|\$[\w\"/]|\bfind_child\s*\(|\bget_tree\(\)\.get_nodes_in_group"
)
FRAME_FUNCS = re.compile(r"^func (_process|_physics_process)\s*\(", re.M)
SKIP = (".godot", ".import", "addons", ".git")


@dataclass
class Finding:
    severity: str  # "high", "medium", "info"
    file: str
    message: str


@dataclass
class Analysis:
    scenes: int = 0
    scripts: int = 0
    textures: int = 0
    biggest_scenes: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _files(root: Path, *suffixes: str) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*"))
        if p.suffix.lower() in suffixes
        and p.is_file()
        and not any(part in SKIP for part in p.relative_to(root).parts)
    ]


def image_size(path: Path) -> tuple[int, int] | None:
    """Width and height from a PNG, JPEG or WebP header; None otherwise."""
    try:
        with path.open("rb") as fh:
            head = fh.read(32)
            if head.startswith(b"\x89PNG"):
                return struct.unpack(">II", head[16:24])
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:16] == b"VP8X":
                w = int.from_bytes(head[24:27], "little") + 1
                h = int.from_bytes(head[27:30], "little") + 1
                return w, h
            if head.startswith(b"\xff\xd8"):
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    length = struct.unpack(">H", fh.read(2))[0]
                    if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                        h, w = struct.unpack(">xHH", fh.read(5))
                        return w, h
                    fh.seek(length - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def _depth(parent: str) -> int:
    """How deep a node is: the root is 1, its children (parent ".") 2, and so on."""
    if not parent:
        return 1
    return 2 if parent == "." else parent.count("/") + 3


def frame_lookups(source: str) -> int:
    """Node lookups inside _process/_physics_process bodies (cache them in @onready)."""
    count = 0
    for match in FRAME_FUNCS.finditer(source):
        body = []
        for line in source[match.end() :].splitlines()[1:]:
            if line.strip() and not line.startswith(("\t", " ")):
                break  # the next top-level declaration
            body.append(line)
        count += sum(bool(LOOKUP.search(line)) for line in body)
    return count


def analyze(root: Path, options: dict[str, Any] | None = None) -> Analysis:
    options = options or {}
    max_nodes = int(options.get("max_nodes", 1000))
    max_depth = int(options.get("max_depth", 12))
    max_lights = int(options.get("max_lights", 8))
    max_texture = int(options.get("max_texture", 4096))
    result = Analysis()
    sizes = []
    for scene in _files(root, ".tscn"):
        text = scene.read_text(errors="replace")
        rel = str(scene.relative_to(root))
        nodes = NODE.findall(text)
        depth = max((_depth(parent) for _, parent in nodes), default=0)
        lights, particles = len(LIGHTS.findall(text)), len(PARTICLES.findall(text))
        result.scenes += 1
        sizes.append({"scene": rel, "nodes": len(nodes), "depth": depth})
        if len(nodes) > max_nodes:
            result.findings.append(
                Finding("high", rel, f"{len(nodes)} nodes: split it into instanced scenes")
            )
        if depth > max_depth:
            result.findings.append(
                Finding("medium", rel, f"nesting {depth} levels deep: flatten the hierarchy")
            )
        if lights > max_lights:
            result.findings.append(
                Finding(
                    "high", rel, f"{lights} real-time lights: bake or limit shadow-casting ones"
                )
            )
        if particles > 10:
            result.findings.append(
                Finding("medium", rel, f"{particles} particle systems in one scene")
            )
    result.biggest_scenes = sorted(sizes, key=lambda s: -s["nodes"])[:5]
    for script in _files(root, ".gd"):
        source = script.read_text(errors="replace")
        rel = str(script.relative_to(root))
        result.scripts += 1
        if lookups := frame_lookups(source):
            result.findings.append(
                Finding(
                    "medium",
                    rel,
                    f"{lookups} node lookup(s) every frame in _process: "
                    "keep the node in an @onready var",
                )
            )
        if re.search(r"^func _process\s*\(", source, re.M) and "set_process(false)" not in source:
            if re.search(
                r"^func _process\s*\([^)]*\)\s*(->\s*\w+\s*)?:\s*\n\s*pass\b", source, re.M
            ):
                result.findings.append(
                    Finding("info", rel, "empty _process: remove it, Godot calls it every frame")
                )
    for image in _files(root, ".png", ".jpg", ".jpeg", ".webp"):
        result.textures += 1
        size = image_size(image)
        if size and max(size) > max_texture:
            result.findings.append(
                Finding(
                    "medium",
                    str(image.relative_to(root)),
                    f"{size[0]}×{size[1]} texture: reduce it or use VRAM compression",
                )
            )
    order = {"high": 0, "medium": 1, "info": 2}
    result.findings.sort(key=lambda f: (order[f.severity], f.file))
    return result


def describe(result: Analysis, language: str) -> str:
    pl = language == "pl"
    head = (
        f"Sceny: {result.scenes}, skrypty: {result.scripts}, tekstury: {result.textures}."
        if pl
        else f"Scenes: {result.scenes}, scripts: {result.scripts}, textures: {result.textures}."
    )
    if not result.findings:
        return head + (" Nic podejrzanego." if pl else " Nothing suspicious.")
    lines = [head]
    for f in result.findings[:20]:
        lines.append(f"[{f.severity}] {f.file}: {f.message}")
    if len(result.findings) > 20:
        lines.append(f"(+{len(result.findings) - 20})")
    return "\n".join(lines)


ADVICE_PROMPT = """\
A static analysis of this Godot project found the following. Read the code and
scenes it points to and advise, in {language}: which three problems matter
most for performance or maintainability, why, and the concrete change for
each. Skip findings that are harmless here. Do not change any files.

{findings}
"""


async def analyze_project(dia: Any, project_name: str, advise: bool = False) -> str:
    """The analysis as text; with ``advise`` an agent reads the code and prioritises."""
    from dia.agents import Mode

    project = dia.config.project(project_name)
    result = analyze(project.path, dia.config.section("godot_analysis"))
    text = describe(result, dia.config.language)
    if not advise or not result.findings:
        return text
    language = {"pl": "Polish", "en": "English"}.get(dia.config.language, "English")
    findings = "\n".join(f"- [{f.severity}] {f.file}: {f.message}" for f in result.findings[:40])
    report = await dia.run_task(
        project.name,
        ADVICE_PROMPT.format(language=language, findings=findings),
        mode=Mode.READ_ONLY,
        run_tests=False,
        details={"analysis": result.to_dict()},
    )
    return text + "\n\n" + (report.task.summary or report.task.error or "")
