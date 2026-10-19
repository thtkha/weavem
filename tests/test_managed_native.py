"""Managed authoring: no host compiler/headers, and behavioral tests on native bytes."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from _support import workspace
from weavem.build import BuildError, build
from weavem.contracts import CompatibilityError, require_supported_runtime
from weavem.native import NativeError, _headers, check_native


class ManagedNativeTests(unittest.TestCase):
    def author(self, root, *, source='def run(value): return value * 2\n', body='self.assertEqual(run(3), 6)'):
        task = root / 'task'; task.mkdir()
        (task / 'task.toml').write_text('[task]\ntask_id="managed.example"\nversion="1.0.0"\nbackend="cython"\nsource="implementation.py"\nexport="run"\n')
        (task / 'implementation.py').write_text(source)
        (task / 'tests').mkdir()
        (task / 'tests/test_task.py').write_text('import unittest\nimport implementation\nfrom implementation import run\n\nclass Tests(unittest.TestCase):\n    def test_behavior(self):\n        '+body+'\n')
        return task

    def test_managed_build_needs_no_configured_compiler_or_headers_and_is_reproducible_here(self):
        with workspace() as temporary, patch.dict(os.environ, {
            'CC': '/unavailable/compiler', 'CXX': '/unavailable/compiler',
            'CPATH': '/unavailable/headers', 'CFLAGS': '-this-would-fail',
        }):
            root = Path(temporary)
            task = self.author(root)
            first = build(task, work_dir=root/'work')
            second = build(task, work_dir=root/'work')
            a = json.loads(first.manifest_path.read_text())
            b = json.loads(second.manifest_path.read_text())
            self.assertEqual(a, b)
            payload = first.root / a['artifact_name']
            self.assertEqual(payload.read_bytes()[:4], b'\x7fELF')
            self.assertNotIn(str(root).encode(), payload.read_bytes())
            self.assertEqual(a['build']['compiler'], 'ziglang==0.17.0')
            self.assertEqual(set(p.name for p in first.root.iterdir()), {'manifest.json', payload.name})

    def test_source_pass_native_behavior_fail_does_not_create_candidate(self):
        with workspace() as temporary:
            root = Path(temporary)
            task = self.author(root, source='import cython\ndef run(): return cython.compiled\n', body='self.assertFalse(run())')
            with self.assertRaisesRegex(BuildError, 'compiled artifact tests failed'):
                build(task, work_dir=root/'work')
            self.assertEqual(list((root/'work').iterdir()), [])

    def test_compiled_suite_cannot_fall_back_to_source(self):
        with workspace() as temporary:
            root = Path(temporary)
            body = "self.assertIn(implementation.__file__.rsplit('.',1)[-1], ('py','so'))\n        if implementation.__file__.endswith('.so'):\n            import sys, importlib\n            del sys.modules['implementation']\n            with self.assertRaises(ModuleNotFoundError): importlib.import_module('implementation')"
            build(self.author(root, body=body), work_dir=root/'work')

    def test_compiled_suite_cannot_mutate_published_bytes(self):
        with workspace() as temporary:
            root = Path(temporary)
            body = "self.assertEqual(run(3),6)\n        if implementation.__file__.endswith('.so'):\n            from pathlib import Path\n            Path(implementation.__file__).write_bytes(b'not an extension')"
            with self.assertRaisesRegex(BuildError, 'mutated|compiled artifact tests failed'):
                build(self.author(root, body=body), work_dir=root/'work')
            self.assertEqual(list((root/'work').iterdir()), [])

    def test_missing_unmatched_headers_fail_without_os_install(self):
        with workspace() as temporary:
            with patch('weavem.native.sysconfig.get_config_vars', return_value={'SOABI': 'not-supported'}), patch('weavem.native.sysconfig.get_path', return_value='/missing'), patch('weavem.native.sysconfig.get_config_h_filename', return_value='/missing/pyconfig.h'):
                with self.assertRaisesRegex(NativeError, 'not supported'):
                    _headers(Path(temporary))

    def test_doctor_checks_available_headers(self):
        with workspace() as temporary:
            result = check_native(Path(temporary))
            self.assertTrue(result['headers'] == 'interpreter'
                            or result['headers'].startswith('cpython-'))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_matching_bundle_is_verified_and_extracted(self):
        import weavem.native as native
        resources = Path(native.__file__).with_name('_native_headers')
        for path in sorted(resources.glob('*.json')):
            record = json.loads(path.read_text())
            with self.subTest(bundle=path.name), workspace() as temporary:
                config = record['config'] | {'SOABI': record['soabi']}
                with patch('weavem.native.sys.version_info', tuple(record['version'])), \
                        patch('weavem.native.sysconfig.get_config_vars', return_value=config):
                    paths, identity = _headers(Path(temporary))
                self.assertEqual(identity, path.stem)
                self.assertTrue((paths[0] / 'Python.h').is_file())
                self.assertTrue((paths[0] / 'pyconfig.h').is_file())

    def test_complete_interpreter_headers_are_used_when_no_bundle_matches(self):
        with workspace() as temporary:
            root = Path(temporary)
            (root / 'Python.h').write_text('/* interpreter header fixture */')
            config = root / 'pyconfig.h'; config.write_text('/* generated fixture */')
            with patch('weavem.native.sysconfig.get_config_vars', return_value={'SOABI': 'another-standard-distribution'}), patch('weavem.native.sysconfig.get_path', return_value=str(root)), patch('weavem.native.sysconfig.get_config_h_filename', return_value=str(config)):
                paths, identity = _headers(root)
            self.assertEqual(paths, [root])
            self.assertEqual(identity, 'interpreter')

    def test_free_threaded_runtime_is_rejected(self):
        with patch('weavem.contracts.sysconfig.get_config_var', return_value=1):
            with self.assertRaisesRegex(CompatibilityError, 'GIL'):
                require_supported_runtime()
