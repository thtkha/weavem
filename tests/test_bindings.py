from __future__ import annotations
import hashlib
from pathlib import Path
import unittest

from _support import workspace
from weavem.bindings import read_bindings, resolve_binding
from weavem.config import resolve_project
from weavem.contracts import ContractError


class BindingTests(unittest.TestCase):
    def test_path_and_released_bindings_are_explicit(self):
        with workspace() as raw:
            root = Path(raw)
            digest = "a" * 64
            (root / "weavem.toml").write_text(
                "[tasks.local]\npath = 'tasks/foo'\n"
                "[tasks.release]\nrelease = 'demo.double==1.0.0'\nsource = 'task-store'\n"
                f"manifest_sha256 = '{digest}'\n")
            bindings = read_bindings(resolve_project(root))
            self.assertEqual(root / "tasks/foo", bindings["local"].path)
            self.assertEqual("demo.double==1.0.0", resolve_binding(bindings, "release").release)

    def test_released_binding_requires_exact_digest_and_no_ambiguous_forms(self):
        with workspace() as raw:
            root = Path(raw)
            (root / "weavem.toml").write_text("[tasks.bad]\nrelease='id==1'\nsource='task-store'\n")
            with self.assertRaisesRegex(ContractError, "manifest_sha256"):
                read_bindings(resolve_project(root))
            (root / "weavem.toml").write_text("[tasks.bad]\npath='x'\nrelease='id==1'\n")
            with self.assertRaisesRegex(ContractError, "exactly"):
                read_bindings(resolve_project(root))

if __name__ == '__main__':
    unittest.main()
