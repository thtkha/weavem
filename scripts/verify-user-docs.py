#!/usr/bin/env python3
"""Execute the marked runnable user documentation against an installed wheel.

This is a deliberately small, stdlib-only release gate.  It converts explicitly
marked file snippets and Bash commands from the two canonical user guides into
one fail-fast shell program.  The resulting work directory is retained as
failure evidence; it is never a source of inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import zipfile
from typing import Any

TIMEOUT_SECONDS = 900
GUIDES = ("users/authoring-guide.md", "users/native-authoring.md")
RUN_MARKER = "<!-- weavem-run -->"
FILE_MARKER = re.compile(r"<!-- weavem-file: ([^ >]+) -->$")
FENCE = re.compile(r"^```([A-Za-z0-9_-]+)?\s*$")
SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")


class GateFailure(RuntimeError):
    """A user-facing tutorial was not runnable as documented."""


@dataclass(frozen=True)
class Block:
    guide: str
    line: int
    kind: str
    content: str
    path: str | None = None


def _wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise GateFailure(f"wheel must contain one dist-info metadata file: {wheel}")
        for line in archive.read(metadata[0]).decode("utf-8").splitlines():
            if line.startswith("Version: "):
                return line.removeprefix("Version: ")
    raise GateFailure(f"wheel has no Version metadata: {wheel}")


def _safe_relative(path: str) -> bool:
    candidate = Path(path)
    return bool(SAFE_RELATIVE.fullmatch(path)) and not candidate.is_absolute() and ".." not in candidate.parts and "." not in candidate.parts


def _heading_ids(page: Path) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    in_fence = False
    for line in page.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        text = re.sub(r"[`*_]", "", match.group(1)).lower()
        slug = re.sub(r"[^a-z0-9 -]", "", text).replace(" ", "-")
        slug = re.sub(r"-+", "-", slug).strip("-")
        number = seen.get(slug, 0)
        seen[slug] = number + 1
        anchors.add(slug if number == 0 else f"{slug}-{number}")
    return anchors


def _official_pages(docs: Path) -> list[Path]:
    # Records are preserved, not ignored: moving a report must not silently
    # leave broken links outside the current user manual.
    pages = sorted(docs.rglob("*.md"))
    readme = docs.parent / "README.md"
    if readme.is_file():
        pages.append(readme)
    return pages


def validate_links(docs: Path) -> None:
    """Reject broken local paths and heading fragments across all audiences."""
    pages = _official_pages(docs)
    for page in pages:
        for raw in MARKDOWN_LINK.findall(page.read_text(encoding="utf-8")):
            target = raw.strip().strip("<>").split(maxsplit=1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            local, separator, fragment = target.partition("#")
            local = local.split("?", 1)[0]
            target_page = page if not local else (page.parent / local).resolve()
            if not target_page.is_file():
                raise GateFailure(f"{page}: broken local documentation link: {raw}")
            if separator and fragment not in _heading_ids(target_page):
                raise GateFailure(f"{page}: broken heading fragment: {raw}")



def parse_guide(path: Path) -> list[Block]:
    """Read only explicitly marked runnable snippets from one guide."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        marker = lines[index].rstrip("\n")
        run = marker == RUN_MARKER
        file_match = FILE_MARKER.fullmatch(marker)
        if not run and file_match is None:
            index += 1
            continue
        marker_line = index + 1
        index += 1
        if index >= len(lines) or not FENCE.fullmatch(lines[index].rstrip("\n")):
            raise GateFailure(f"{path}:{marker_line}: marker must be immediately followed by a fenced block")
        language = FENCE.fullmatch(lines[index].rstrip("\n")).group(1)  # type: ignore[union-attr]
        index += 1
        start = index
        while index < len(lines) and lines[index].rstrip("\n") != "```":
            index += 1
        if index == len(lines):
            raise GateFailure(f"{path}:{marker_line}: unterminated fenced block")
        content = "".join(lines[start:index])
        index += 1
        if run:
            if language not in {"bash", "sh"}:
                raise GateFailure(f"{path}:{marker_line}: {RUN_MARKER} requires a bash fenced block")
            blocks.append(Block(path.name, marker_line, "run", content))
        else:
            assert file_match is not None
            target = file_match.group(1)
            if language not in {"python", "toml"}:
                raise GateFailure(f"{path}:{marker_line}: file marker requires a python or toml fenced block")
            if not _safe_relative(target):
                raise GateFailure(f"{path}:{marker_line}: unsafe relative tutorial file path: {target!r}")
            blocks.append(Block(path.name, marker_line, "file", content, target))
    return blocks


def _delimiter(content: str, ordinal: int) -> str:
    delimiter = f"WEAVEM_DOC_BLOCK_{ordinal}"
    while any(line.rstrip("\n") == delimiter for line in content.splitlines(keepends=True)):
        delimiter += "_X"
    return delimiter


def render_shell(blocks: list[Block]) -> str:
    """Render a single shell that interleaves file writes and documented commands."""
    program = ["#!/usr/bin/env bash\n", "set -Eeuo pipefail\n", "\n"]
    for ordinal, block in enumerate(blocks, 1):
        program.append(f"# {block.guide}:{block.line}\n")
        if block.kind == "run":
            program.append(block.content)
            if not block.content.endswith("\n"):
                program.append("\n")
        else:
            assert block.path is not None
            parent = Path(block.path).parent
            if str(parent) != ".":
                program.append(f"test -d {parent.as_posix()!r}\n")
            delimiter = _delimiter(block.content, ordinal)
            program.append(f"cat > {block.path!r} <<'{delimiter}'\n")
            program.append(block.content)
            if not block.content.endswith("\n"):
                program.append("\n")
            program.append(f"{delimiter}\n")
        program.append("\n")
    return "".join(program)


def _environment(root: Path, wheel: Path) -> dict[str, str]:
    artifacts = root / "artifacts"
    for directory in (artifacts / "home", artifacts / "tmp", artifacts / "prefect", artifacts / "weavem", artifacts / "pip-cache"):
        directory.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith("PREFECT_") or key in {"PYTHONPATH", "PYTHONHOME", "WEAVEM_STORE", "WEAVEM_ARTIFACTS_DIR"}:
            environment.pop(key)
    # ``resolve()`` would follow a virtualenv's python symlink into the base
    # interpreter and lose its console scripts from PATH.
    executable_dir = str(Path(sys.executable).absolute().parent)
    environment.update({
        "PATH": executable_dir + os.pathsep + environment.get("PATH", ""),
        "VIRTUAL_ENV": str(Path(executable_dir).parent),
        "HOME": str(artifacts / "home"),
        "TMPDIR": str(artifacts / "tmp"),
        "PIP_CACHE_DIR": str(artifacts / "pip-cache"),
        "PREFECT_HOME": str(artifacts / "prefect"),
        "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "WEAVEM_WHEEL": str(wheel),
    })
    return environment


def _assert_installed_wheel(root: Path, wheel: Path) -> dict[str, str]:
    import weavem

    origin = Path(weavem.__file__).resolve()
    prefix = Path(sys.prefix).resolve()
    if not origin.is_relative_to(prefix) or not any(part in {"site-packages", "dist-packages"} for part in origin.parts):
        raise GateFailure(f"weavem must import from the active installed wheel, got {origin}")
    if origin.is_relative_to(root.resolve()) or "/src/weavem/" in f"{origin}/":
        raise GateFailure(f"weavem import is not isolated from the checkout: {origin}")
    expected = _wheel_version(wheel)
    actual = importlib.metadata.version("weavem")
    if actual != expected:
        raise GateFailure(f"installed Weavem {actual} does not match wheel version {expected}")
    return {"wheel": str(wheel), "wheel_version": expected, "weavem_origin": str(origin), "python": sys.version, "executable": sys.executable}


def _manifests(store: Path) -> list[tuple[Path, dict[str, Any]]]:
    found = []
    for path in store.rglob("manifest.json"):
        try:
            found.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            raise GateFailure(f"invalid published manifest: {path}") from exc
    return found


def _assert_tutorial_end_state(root: Path, environment: dict[str, str]) -> dict[str, Any]:
    consumer = root / "consumer"
    store = consumer / "task-store"
    author = root / "author"
    consumer_python = root / ".consumer-venv" / "bin" / "python"
    if author.exists():
        raise GateFailure("tutorial must hide the author project before the final consumer check")
    if not consumer_python.is_file():
        raise GateFailure("tutorial did not create .consumer-venv/bin/python")
    manifests = _manifests(store)
    task_versions = {data.get("version") for _, data in manifests if data.get("kind") == "task" or "backend" in data}
    flow_versions = {data.get("version") for _, data in manifests if data.get("kind") == "flow" or "tasks" in data}
    if not {"1.0.0", "1.1.0"}.issubset(task_versions):
        raise GateFailure(f"consumer store must contain task releases 1.0.0 and 1.1.0, found {sorted(task_versions)}")
    if not {"1.0.0", "1.1.0"}.issubset(flow_versions):
        raise GateFailure(f"consumer store must contain flow releases 1.0.0 and 1.1.0, found {sorted(flow_versions)}")
    native = [(path, data) for path, data in manifests if data.get("backend") == "cython" and data.get("version") == "1.1.0"]
    if len(native) != 1:
        raise GateFailure("consumer store must contain exactly one 1.1.0 native task manifest")
    manifest_path, manifest = native[0]
    payload = manifest_path.parent / str(manifest.get("artifact_name", ""))
    if not payload.is_file() or payload.suffix != ".so":
        raise GateFailure("tutorial native release does not contain a shared-object payload")
    inspect = (
        "import json,pathlib,sys\n"
        "from weavem import task\n"
        "store=pathlib.Path(sys.argv[1]).resolve()\n"
        "manifest=json.loads(next((store/'text.normalize'/'1.1.0').glob('*/manifest.json')).read_text())\n"
        "value=task('text.normalize','1.1.0',store=store).fn('  Hello   WORLD  ')\n"
        "module=sys.modules[manifest['module_leaf']]\n"
        "path=pathlib.Path(module.__file__).resolve()\n"
        "assert value == 'hello world', value\n"
        "assert path.is_relative_to(store) and path.suffix == '.so', path\n"
        "print(json.dumps({'value': value, 'module': str(path)}))\n"
    )
    result = subprocess.run([str(consumer_python), "-I", "-c", inspect, str(store)], cwd=consumer, env=environment,
                            text=True, capture_output=True, check=False, timeout=TIMEOUT_SECONDS)
    (root / "consumer-native.stdout").write_text(result.stdout or "", encoding="utf-8")
    (root / "consumer-native.stderr").write_text(result.stderr or "", encoding="utf-8")
    if result.returncode:
        raise GateFailure(f"consumer native task inspection failed: {(result.stderr or result.stdout).strip()}")
    try:
        native_result = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure("consumer native task inspection did not return JSON") from exc
    flow = subprocess.run([str(consumer_python), "-I", "-m", "weavem", "flow", "run", "text.process_documents==1.1.0", "--release", "--store", str(store), "--params", '{"text":" Hello WORLD "}'], cwd=consumer, env=environment, text=True, capture_output=True, check=False, timeout=TIMEOUT_SECONDS)
    (root / "consumer-flow.stdout").write_text(flow.stdout or "", encoding="utf-8")
    (root / "consumer-flow.stderr").write_text(flow.stderr or "", encoding="utf-8")
    if flow.returncode:
        raise GateFailure(f"consumer released native flow failed: {(flow.stderr or flow.stdout).strip()}")
    try:
        flow_value = json.loads(flow.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure("consumer released native flow did not return JSON") from exc
    if flow_value != "hello world":
        raise GateFailure(f"consumer released native flow returned {flow_value!r}, expected 'hello world'")
    return {"native_task": native_result, "native_flow_result": flow_value, "store_manifest_count": len(manifests)}


def run(docs: Path, wheel: Path, root: Path) -> dict[str, Any]:
    environment = _environment(root, wheel)
    result: dict[str, Any] = {"status": "running", "metadata": _assert_installed_wheel(root, wheel)}
    try:
        # The tutorials assume a workspace-local activated environment.  CI has
        # already installed the exact wheel in sys.prefix; expose that same
        # environment at the documented workspace name without copying it.
        workspace_venv = root / ".venv"
        workspace_venv.symlink_to(Path(sys.prefix).resolve(), target_is_directory=True)
        validate_links(docs)
        blocks: list[Block] = []
        for name in GUIDES:
            guide = docs / name
            if not guide.is_file():
                raise GateFailure(f"missing canonical guide: {guide}")
            blocks.extend(parse_guide(guide))
        if not any(block.kind == "run" for block in blocks) or not any(block.kind == "file" for block in blocks):
            raise GateFailure("canonical guides must contain marked runnable commands and marked file contents")
        program = render_shell(blocks)
        shell = root / "tutorial.sh"
        shell.write_text(program, encoding="utf-8")
        shell.chmod(0o700)
        started = time.time()
        stdout_path, stderr_path = root / "tutorial.stdout", root / "tutorial.stderr"
        # Prefect's local server may outlive an individual flow command.  Do not
        # use capture_output here: its inherited pipe can keep communicate()
        # waiting for EOF after Bash has completed.
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            try:
                shell_result = subprocess.run(["bash", str(shell)], cwd=root, env=environment, text=True,
                                              stdout=stdout, stderr=stderr, check=False, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise GateFailure(f"documented tutorial timed out after {TIMEOUT_SECONDS} seconds") from exc
        result["shell"] = {"returncode": shell_result.returncode, "elapsed_seconds": round(time.time() - started, 3)}
        if shell_result.returncode:
            detail = (stderr_path.read_text(encoding="utf-8") or stdout_path.read_text(encoding="utf-8")).strip()
            raise GateFailure(f"documented tutorial returned {shell_result.returncode}: {detail}")
        author = root / "author"
        hidden_author = root / "author-hidden"
        if not author.is_dir() or hidden_author.exists():
            raise GateFailure("tutorial did not leave an author project ready for the source-removal check")
        author.rename(hidden_author)
        result["tutorial"] = _assert_tutorial_end_state(root, environment)
        result["status"] = "passed"
        return result
    finally:
        (root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", required=True, type=Path, help="directory containing canonical Markdown guides")
    parser.add_argument("--wheel", required=True, type=Path, help="exact installed Weavem wheel used by the tutorial")
    parser.add_argument("--work-dir", required=True, type=Path, help="new absent directory for retained evidence")
    args = parser.parse_args()
    docs, wheel, root = args.docs.resolve(), args.wheel.resolve(), args.work_dir.resolve()
    if not docs.is_dir():
        parser.error(f"--docs must be an existing directory: {docs}")
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error(f"--wheel must be an existing wheel: {wheel}")
    if root.exists() or not root.parent.is_dir():
        parser.error("--work-dir must be a new directory whose parent exists")
    root.mkdir()
    try:
        summary = run(docs, wheel, root)
    except BaseException as exc:
        result_path = root / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        result.update({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()})
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"user documentation verification failed; evidence retained in {root}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
