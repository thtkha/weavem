import json
from pathlib import Path
import unittest
from tests._support import workspace
from weavem.config import resolve_project
from weavem.project import Project
from weavem.editor_flows import list_flows, open_flow, save_flow
from weavem.contracts import ContractError

class FlowDiscoveryTests(unittest.TestCase):
    def fixture(self, root):
        (root/'weavem.toml').write_text('[weavem]\nflow_paths = ["pipelines", "extra", "pipelines/."]\n')
        (root/'pipelines').mkdir(); (root/'extra').mkdir()
        (root/'extra'/'existing.toml').write_text('[flow]\nflow_id="existing"\nversion="1.0.0"\nsource="implementation.py"\nexport="existing"\ntasks=[]\n')
        with (root/'weavem.toml').open('a') as f: f.write('[tasks.one]\npath="tasks/one"\n')
        task=root/'tasks/one'; task.mkdir(parents=True)
        (task/'task.toml').write_text('[task]\ntask_id="demo.one"\nversion="1.0.0"\nbackend="python"\nsource="task.py"\ninputs=[]\noutput="object"\n')
        (task/'task.py').write_text('def run(): return 1\n')
        (root/'extra'/'existing.toml').write_text((root/'extra'/'existing.toml').read_text().replace('tasks=[]','tasks=["one"]'))
        (root/'extra'/'implementation.py').write_text('from weavem import flow, task\none = task("one")\n@flow\ndef existing():\n    result = one()\n    return {"result": result}\n')
    def test_shared_discovery_and_original_save_location(self):
        with workspace() as raw:
            root=Path(raw); self.fixture(root)
            self.assertEqual(resolve_project(root).flow_paths,(root/'pipelines',root/'extra'))
            (root/'extra/nested').mkdir()
            (root/'extra/nested/ignored.toml').write_text('not valid TOML [')
            self.assertEqual([x['name'] for x in list_flows(root)],['existing'])
            self.assertEqual(Path(Project.open(root).metadata()['flows'][0]['path']),root/'extra/existing.toml')
            opened=open_flow('existing',root)
            import os
            from unittest.mock import patch
            with patch('weavem.editor_flows.os.replace', wraps=os.replace) as replace:
                save_flow('existing',opened['graph'],opened['layout'],opened['revision'],root)
            self.assertIn(root/'extra/.weavem-editor-existing.journal',[Path(c.args[1]) for c in replace.call_args_list])
            self.assertTrue((root/'extra/implementation.py').exists())
            self.assertFalse((root/'pipelines/existing.py').exists())
    def test_collision_is_explicit(self):
        with workspace() as raw:
            root=Path(raw);self.fixture(root)
            (root/'pipelines/existing.toml').write_text((root/'extra/existing.toml').read_text())
            with self.assertRaisesRegex(ValueError,'ambiguous.*existing'):
                list_flows(root)
    def test_invalid_config(self):
        with workspace() as raw:
            root=Path(raw)
            for value in ['[]','"flows"','[""]','[false]']:
                (root/'weavem.toml').write_text('[weavem]\nflow_paths='+value)
                with self.assertRaises(ContractError):resolve_project(root)
    def test_no_import_and_invalid_metadata_diagnostic(self):
        with workspace() as raw:
            root=Path(raw);self.fixture(root)
            source=root/'extra/implementation.py'
            source.write_text('raise RuntimeError("must not import during discovery")\n')
            self.assertEqual(len(Project.open(root).metadata()['flows']),1)
            self.assertFalse(list_flows(root)[0]['editable'])
            (root/'extra/existing.toml').write_text('invalid = [')
            self.assertTrue(list_flows(root)[0]['reason'])
            with self.assertRaises(ContractError):Project.open(root).metadata()
    def test_new_flow_uses_first_root_and_absolute_paths(self):
        with workspace() as raw:
            root=Path(raw);self.fixture(root)
            opened=open_flow('existing',root)
            graph={**opened['graph'],'name':'new_flow'}
            save_flow('new_flow',graph,None,None,root)
            self.assertTrue((root/'pipelines/new_flow.py').is_file())
            from weavem.flows import _spec
            _, source=_spec(resolve_project(root),'existing')
            self.assertEqual(source,root/'extra/implementation.py')
            (root/'weavem.toml').write_text('[weavem]\nflow_paths=['+json.dumps(str(root/'extra'))+']\n[tasks.one]\npath="tasks/one"\n')
            self.assertEqual(len(list_flows(root)),1)
    def test_symlinked_roots_and_missing_source_rejected(self):
        with workspace() as raw:
            root=Path(raw);self.fixture(root)
            (root/'link').symlink_to(root/'extra',target_is_directory=True)
            with (root/'weavem.toml').open('w') as f:f.write('[weavem]\nflow_paths=["link"]\n')
            with self.assertRaises(ContractError):resolve_project(root)

    def test_cli_scaffold_uses_configured_root_and_portable_loader_test(self):
        from argparse import Namespace
        from weavem.cli import _new_flow
        from weavem.flows import validate_source_flow
        with workspace() as raw:
            root=Path(raw);self.fixture(root)
            _new_flow(Namespace(name='scaffold',project=str(root)))
            self.assertTrue((root/'pipelines/scaffold.toml').exists())
            generated=(root/'tests/flows/scaffold/test_flow.py').read_text()
            self.assertIn('load_local_flow',generated)
            self.assertNotIn(str(root),generated)
            validate_source_flow('scaffold',project=root)
