"""Focused regression tests for the official user-documentation smoke gate."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from _support import ROOT, workspace


def _script_module():
    path = ROOT / "scripts" / "verify-user-docs.py"
    spec = importlib.util.spec_from_file_location("verify_user_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerifyUserDocsTests(unittest.TestCase):
    def test_repository_documentation_is_partitioned_and_linked(self) -> None:
        module = _script_module()
        docs = ROOT / "docs"
        self.assertEqual(["index.md"], sorted(path.name for path in docs.glob("*.md")))
        for audience in ("users", "maintainers", "project"):
            self.assertTrue((docs / audience / "index.md").is_file(), audience)
        for report in (
            "developer-simulation.md", "blind-acceptance-2026-10-21.md",
            "runtime-compatibility-acceptance-2026-10-21.md",
            "cache-tolerance-acceptance-2026-10-21.md",
            "release-readiness-2026-10-26.md", "native-history.md",
        ):
            self.assertTrue((docs / "project" / "history" / report).is_file(), report)
        for guide in module.GUIDES:
            self.assertEqual("users", Path(guide).parts[0])
            self.assertTrue(module.parse_guide(docs / guide), guide)
        module.validate_links(docs)

    def test_public_a2_docs_preserve_exact_artifact_and_unreleased_boundary(self) -> None:
        getting_started = (ROOT / "docs/users/getting-started.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        release = (ROOT / "docs/maintainers/releasing.md").read_text(encoding="utf-8")
        legacy = (ROOT / "docs/maintainers/releasing-private-legacy.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("python -m pip install --pre 'weavem==0.1.0a2'", getting_started)
        self.assertIn('export WEAVEM_WHEEL="$PWD/downloads/weavem-0.1.0a2-py3-none-any.whl"', getting_started)
        self.assertIn("prototype/node-editor", readme)
        self.assertIn("not part of `0.1.0a2`", readme)
        self.assertIn("518877f1dc2c20c34ed3c0aeb9144a4e99d8a6ab4547db103130c475b9aa2f95", release)
        self.assertIn("publish-pypi.yml", release)
        self.assertIn("| Status | Deprecated |", legacy)
        self.assertIn("khaa.dev@gmail.com", security)

    def test_link_validation_covers_every_audience_and_archived_records(self) -> None:
        module = _script_module()
        for folder in ("users", "maintainers", "project", "project/history"):
            with self.subTest(folder=folder), workspace("docs-") as raw:
                docs = Path(raw) / "docs"
                page = docs / folder / "record.md"
                page.parent.mkdir(parents=True)
                page.write_text("[missing](gone.md)\n", encoding="utf-8")
                with self.assertRaisesRegex(module.GateFailure, "broken local"):
                    module.validate_links(docs)

    def _guide(self, root: Path, text: str) -> Path:
        path = root / "guide.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parser_preserves_marked_blocks_in_document_order(self) -> None:
        module = _script_module()
        with workspace("docs-") as raw:
            root = Path(raw)
            guide = self._guide(root, """intro
<!-- weavem-run -->
```bash
mkdir task
```
<!-- weavem-file: task/implementation.py -->
```python
def run(value):
    return value
```
<!-- weavem-run -->
```bash
python -m unittest
```
""")
            blocks = module.parse_guide(guide)
            self.assertEqual(["run", "file", "run"], [block.kind for block in blocks])
            self.assertEqual("task/implementation.py", blocks[1].path)
            rendered = module.render_shell(blocks)
            self.assertLess(rendered.index("mkdir task"), rendered.index("cat > 'task/implementation.py'"))
            self.assertLess(rendered.index("cat > 'task/implementation.py'"), rendered.index("python -m unittest"))

    def test_parser_rejects_unfenced_marker_and_unsafe_file_path(self) -> None:
        module = _script_module()
        with workspace("docs-") as raw:
            root = Path(raw)
            malformed = self._guide(root, "<!-- weavem-run -->\nnot fenced\n")
            with self.assertRaisesRegex(module.GateFailure, "immediately"):
                module.parse_guide(malformed)
            unsafe = self._guide(root, "<!-- weavem-file: ../outside.py -->\n```python\npass\n```\n")
            with self.assertRaisesRegex(module.GateFailure, "unsafe"):
                module.parse_guide(unsafe)

    def test_link_validation_rejects_a_missing_local_page(self) -> None:
        module = _script_module()
        with workspace("docs-") as raw:
            root = Path(raw)
            docs = root / "docs"
            docs.mkdir()
            (docs / "authoring-guide.md").write_text("[missing](gone.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(module.GateFailure, "broken local"):
                module.validate_links(docs)

    def test_link_validation_rejects_a_missing_heading_fragment(self) -> None:
        module = _script_module()
        with workspace("docs-") as raw:
            root = Path(raw)
            docs = root / "docs"
            docs.mkdir()
            (docs / "index.md").write_text("# Start here\n[wrong](index.md#not-present)\n", encoding="utf-8")
            with self.assertRaisesRegex(module.GateFailure, "broken heading"):
                module.validate_links(docs)

    def test_file_rendering_requires_an_existing_parent_directory(self) -> None:
        module = _script_module()
        block = module.Block("guide.md", 1, "file", "value = 1\n", "missing/file.py")
        program = module.render_shell([block])
        self.assertIn("test -d 'missing'", program)
        self.assertIn("cat > 'missing/file.py'", program)

    def test_environment_drops_ambient_runtime_configuration_and_uses_exact_wheel(self) -> None:
        module = _script_module()
        inherited = {
            "PREFECT_API_URL": "https://example.invalid",
            "PREFECT_PROFILES_PATH": "/unrelated/profiles.toml",
            "PYTHONPATH": "/unrelated/source",
            "PYTHONHOME": "/unrelated/python",
            "WEAVEM_STORE": "/unrelated/store",
            "WEAVEM_ARTIFACTS_DIR": "/unrelated/artifacts",
            "PIP_CONFIG_FILE": "/user-controlled/pip.conf",
        }
        with workspace("docs-") as raw, patch.dict(os.environ, inherited):
            root = Path(raw)
            wheel = root / "weavem.whl"
            wheel.write_bytes(b"placeholder")
            environment = module._environment(root, wheel)
            for key in inherited:
                if key == "PIP_CONFIG_FILE":
                    self.assertEqual(inherited[key], environment[key])
                    continue
                self.assertNotIn(key, environment)
            self.assertNotIn("WEAVEM_ARTIFACTS_DIR", environment)
            self.assertEqual(str(wheel), environment["WEAVEM_WHEEL"])
            self.assertEqual(str(root / "artifacts" / "prefect"), environment["PREFECT_HOME"])
            self.assertEqual(str(Path(module.sys.executable).absolute().parent), environment["PATH"].split(os.pathsep)[0])

    def test_final_state_rejects_author_project_left_visible(self) -> None:
        module = _script_module()
        with workspace("docs-") as raw:
            root = Path(raw)
            (root / "author").mkdir()
            with self.assertRaisesRegex(module.GateFailure, "hide the author"):
                module._assert_tutorial_end_state(root, {})


if __name__ == "__main__":
    unittest.main()
