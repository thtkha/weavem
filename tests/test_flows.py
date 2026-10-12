from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

from _support import workspace
from weavem.flow_contracts import FlowManifest, FlowSpec


class FlowContractTests(unittest.TestCase):
    def test_flow_spec_and_manifest_are_strict(self):
        spec = FlowSpec.from_mapping({'flow_id':'demo.flow','version':'1.0.0','source':'demo.py','export':'demo','tasks':['double']})
        self.assertEqual('demo.flow', spec.flow_id)
        manifest = FlowManifest(1, 'flow', 'demo.flow', '1.0.0', '_weavem_flow_demo_0123456789abcdef',
            'demo', '_weavem_flow_demo_0123456789abcdef.py', '0'*64, 1,
            __import__('sys').implementation.cache_tag, __import__('sysconfig').get_platform(),
            ({'alias':'double','task_id':'flowtests.double','version':'1.0.0','manifest_sha256':'1'*64},))
        self.assertEqual(manifest, FlowManifest.from_json_bytes(manifest.to_json_bytes()))
        with self.assertRaises(ValueError):
            FlowSpec.from_mapping({'flow_id':'x','version':'1','source':'../x.py','export':'x','tasks':['a']})


@unittest.skipUnless(importlib.util.find_spec('prefect'), 'Prefect is not installed in this shell')
class FlowLifecycleTests(unittest.TestCase):
    def test_build_and_publish_flow_preserves_candidate_and_pins_task(self):
        from weavem.build import build, publish
        from weavem.bindings import manifest_digest
        from weavem.flows import build_flow, load_flow, publish_flow
        from weavem.store import LocalStore
        with workspace() as raw:
            root = Path(raw); task_root = root / 'tasks' / 'double'; task_root.mkdir(parents=True)
            (task_root/'task.toml').write_text('[task]\ntask_id="flowtests.double"\nversion="1.0.0"\nsource="implementation.py"\nexport="run"\n')
            (task_root/'implementation.py').write_text('def run(value): return value * 2\n')
            (task_root/'tests').mkdir(); (task_root/'tests'/'test_task.py').write_text('import unittest\nfrom implementation import run\nclass T(unittest.TestCase):\n def test_x(self): self.assertEqual(run(2),4)\n')
            (root/'weavem.toml').write_text('[weavem]\nstore="store"\nwork_dir=".artifacts"\n')
            store=LocalStore(root/'store'); task_ref=publish(build(task_root, project=root),store=store)
            digest=manifest_digest(task_ref.manifest_path)
            with (root/'weavem.toml').open('a') as f: f.write(f'\n[tasks.double]\nrelease="flowtests.double==1.0.0"\nsource="task-store"\nmanifest_sha256="{digest}"\n')
            (root/'flows').mkdir(); (root/'flows'/'demo.toml').write_text('[flow]\nflow_id="demo"\nversion="1.0.0"\nsource="demo.py"\nexport="demo"\ntasks=["double"]\n')
            (root/'flows'/'demo.py').write_text('from weavem import flow, task\ndouble=task("double")\n@flow\ndef demo(value): return double.fn(value)\n')
            testdir=root/'tests'/'flows'/'demo'; testdir.mkdir(parents=True); (testdir/'test_source.py').write_text('import unittest\nfrom flows.demo import demo\nclass T(unittest.TestCase):\n def test_import(self): self.assertIsNotNone(demo)\n')
            candidate=build_flow('demo',project=root); ref=publish_flow(candidate,store=store)
            self.assertTrue(candidate.root.is_dir()); self.assertEqual(6,load_flow('demo','1.0.0',store=store).fn(3))
            self.assertEqual(ref.root, publish_flow(candidate,store=store).root)

    def test_load_local_flow_uses_selected_project_for_path_binding(self):
        from weavem.flows import load_local_flow
        with workspace() as raw:
            root = Path(raw); task_root = root / 'tasks' / 'local'; task_root.mkdir(parents=True)
            (task_root/'task.toml').write_text('[task]\ntask_id="demo.local"\nversion="1.0.0"\n')
            (task_root/'implementation.py').write_text('def run(value): return value\n')
            (task_root/'tests').mkdir(); (task_root/'tests'/'test_task.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.assertTrue(True)\n')
            (root/'weavem.toml').write_text('[tasks.local]\npath="tasks/local"\n')
            (root/'flows').mkdir(); (root/'flows'/'local.toml').write_text('[flow]\nflow_id="demo.localflow"\nversion="1.0.0"\nsource="local.py"\nexport="local"\ntasks=["local"]\n')
            (root/'flows'/'local.py').write_text('from weavem import flow, task\nlocal_task=task("local")\n@flow\ndef local(value): return local_task.fn(value)\n')
            self.assertEqual(7, load_local_flow('local', project=root).fn(7))

if __name__ == '__main__': unittest.main()
