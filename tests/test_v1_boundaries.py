"""Negative and configuration checks for the explicit development/release boundary."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import chdir, redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import sysconfig
import unittest
from unittest.mock import patch

from _support import workspace
from test_store_runtime import stage
from weavem import task
from weavem.bindings import manifest_digest, read_bindings
from weavem.cli import main
from weavem.config import resolve_project
from weavem.contracts import ContractError, IntegrityError, ManifestError, StoreError
from weavem.flow_contracts import FlowManifest
from weavem.flows import (FlowError, FlowStore, build_flow, load_flow, load_local_flow,
                          publish_flow, test_flow, validate_source_flow)
from weavem.store import ArtifactRef, LocalStore
from weavem.runtime import bound_tasks


class V1BoundaryTests(unittest.TestCase):
    def test_release_alias_ignores_ambient_config_and_fails_closed_outside_context(self):
        with workspace() as tmp:
            root = Path(tmp)
            ref = ArtifactRef(stage(root/'candidate', task_id='boundary.no-ambient-config'))
            (root/'weavem.toml').write_text('not valid toml !!!')
            with chdir(root), bound_tasks({'selected': (ref, manifest_digest(ref.manifest_path))}):
                wrapped = task('selected')
                self.assertEqual(wrapped.fn(3), 6)
            with self.assertRaisesRegex(IntegrityError, 'outside'):
                wrapped.fn(3)

    def _project(self, root):
        self.assertEqual(main(["project", "new", str(root)]), 0)
        return root

    def _cli(self, root, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return main(["--project", str(root), *args])

    def _flow(self, root, source=None, aliases='[]'):
        self.assertEqual(self._cli(root, "flow", "new", "report"), 0)
        if source:
            (root / "flows/report.py").write_text(source)
        p = root / "flows/report.toml"
        p.write_text(p.read_text().replace('tasks = []', f'tasks = {aliases}'))
        return p

    def _flow_candidate(self, directory, *, value=1):
        directory.mkdir()
        raw = f'from weavem import flow\n@flow\ndef report(): return {value}\n'.encode()
        leaf = '_weavem_flow_' + hashlib.sha256(raw).hexdigest()
        manifest = FlowManifest(1, 'flow', 'boundary.flow', '1', leaf, 'report', leaf+'.py',
                                hashlib.sha256(raw).hexdigest(), len(raw), sys.implementation.cache_tag,
                                sysconfig.get_platform(), ())
        (directory / 'manifest.json').write_bytes(manifest.to_json_bytes())
        (directory / manifest.artifact_name).write_bytes(raw)
        return ArtifactRef(directory)

    def test_binding_replacement_preserves_other_settings_and_rejects_invalid_tables(self):
        with workspace() as tmp:
            root = self._project(Path(tmp)/'project')
            self.assertEqual(self._cli(root, 'task', 'new', str(root/'tasks/one')), 0)
            config = root/'weavem.toml'
            config.write_text('# important\n[weavem]\nwork_dir="scratch"\n\n[tasks.other]\npath="tasks/one"\n')
            for _ in range(2):
                self.assertEqual(self._cli(root, 'task', 'use', 'one', '--path', 'tasks/one'), 0)
            self.assertIn('# important',config.read_text())
            self.assertIn('work_dir="scratch"',config.read_text())
            bindings = read_bindings(resolve_project(root))
            self.assertEqual(set(bindings), {'one','other'})
            config.write_text(config.read_text()+'\n[tasks.one.metadata]\nextra=true\n')
            old = config.read_bytes()
            self.assertEqual(self._cli(root, 'task', 'use', 'one', '--path', 'tasks/one'), 2)
            self.assertEqual(old, config.read_bytes())

    def test_local_and_released_aliases_coexist_and_missing_local_never_falls_back(self):
        with workspace() as tmp:
            root = self._project(Path(tmp)/'project')
            source = root/'tasks/local'
            self.assertEqual(self._cli(root,'task','new',str(source)),0)
            ref = LocalStore(root/'task-store').publish(stage(Path(tmp)/'candidate',task_id='boundary.mixed'))
            self.assertEqual(self._cli(root,'task','use','local','--path','tasks/local'),0)
            self.assertEqual(self._cli(root,'task','use','stable','--release','boundary.mixed==1.0.0'),0)
            local = task('local',project=root); stable=task('stable',project=root)
            self.assertEqual(local.fn(3),3); self.assertEqual(stable.fn(3),6)
            (source/'implementation.py').write_text('def run(value): return value + 9\n')
            self.assertEqual(local.fn(3),12); self.assertEqual(stable.fn(3),6)
            shutil.rmtree(source)
            with self.assertRaises(Exception): local.fn(3)
            self.assertEqual(manifest_digest(ref.manifest_path),read_bindings(resolve_project(root))['stable'].manifest_sha256)

    def test_native_local_task_compiles_without_publishing_or_running_author_tests(self):
        with workspace() as tmp:
            root = self._project(Path(tmp)/'project')
            source = root/'tasks/native'
            self.assertEqual(self._cli(root,'task','new',str(source),'--backend','cython'),0)
            shutil.rmtree(source/'tests')
            self.assertEqual(self._cli(root,'task','use','native','--path','tasks/native'),0)
            work = resolve_project(root).work_dir
            existing_work = set(work.iterdir()) if work.exists() else set()
            wrapped=task('native',project=root)
            self.assertEqual(wrapped.fn(3),3)
            (source/'implementation.py').write_text('def run(value): return value * 3\n')
            self.assertEqual(wrapped.fn(3),9)
            self.assertFalse((root/'task-store').exists())
            self.assertEqual(set(work.iterdir()), existing_work)

    def test_local_flow_source_edits_and_in_function_aliases_honor_project(self):
        with workspace() as tmp:
            root=self._project(Path(tmp)/'project')
            self.assertEqual(self._cli(root,'task','new',str(root/'tasks/local')),0)
            self.assertEqual(self._cli(root,'task','use','local','--path','tasks/local'),0)
            self._flow(root,'from weavem import flow, task\n@flow\ndef report(x): return task("local").fn(x)\n','["local"]')
            validate_source_flow('report',project=root)
            self.assertEqual(load_local_flow('report',project=root).fn(3),3)
            (root/'flows/report.py').write_text('from weavem import flow\n@flow\ndef report(x): return x+7\n')
            self.assertEqual(load_local_flow('report',project=root).fn(3),10)
            self.assertFalse((root/'.artifacts').exists())

    def test_shared_source_flow_tests_execute_recorded_pins(self):
        with workspace() as tmp:
            root=self._project(Path(tmp)/'project')
            LocalStore(Path(tmp)/'shared').publish(stage(Path(tmp)/'candidate',task_id='boundary.shared'))
            self.assertEqual(self._cli(root,'task','use','selected','--release','boundary.shared==1.0.0','--from','../shared'),0)
            self._flow(root,'from weavem import flow, task\nselected=task("selected")\n@flow\ndef report(): return selected.fn(3)\n','["selected"]')
            (root/'tests/flows/report/test_flow.py').write_text('import unittest\nfrom flows.report import report\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(report.fn(),6)\n')
            test_flow('report',project=root)
            candidate=build_flow('report',project=root)
            with self.assertRaises(StoreError): publish_flow(candidate,project=root)
            self.assertFalse((root/'task-store').exists())
            publish_flow(candidate,store=Path(tmp)/'shared')
            self.assertEqual(load_flow('report','0.1.0',store=Path(tmp)/'shared').fn(),6)

    def test_empty_flow_tests_and_undeclared_aliases_are_rejected(self):
        with workspace() as tmp:
            root=self._project(Path(tmp)/'project'); self._flow(root)
            (root/'tests/flows/report/test_flow.py').write_text('')
            with self.assertRaisesRegex(FlowError,'at least one'): build_flow('report',project=root)
            (root/'tests/flows/report/test_flow.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
            (root/'flows/report.py').write_text('from weavem import flow, task\nmissing=task("missing")\n@flow\ndef report(): return None\n')
            with self.assertRaisesRegex(FlowError,'declared task alias'): build_flow('report',project=root)

    def test_flow_contract_rejects_malformed_fields_and_duplicate_aliases(self):
        with workspace() as tmp:
            ref=self._flow_candidate(Path(tmp)/'candidate')
            raw=json.loads(ref.manifest_path.read_bytes())
            dep={'alias':'x','task_id':'boundary.dep','version':'1','manifest_sha256':'a'*64}
            for change in ({'schema':True},{'export':42},{'task_dependencies':None},
                           {'task_dependencies':[None]},{'task_dependencies':[dep,dep]},
                           {'task_dependencies':[dep|{'task_id':'../escape'}]}):
                with self.subTest(change=change), self.assertRaises(ManifestError):
                    FlowManifest.from_json_bytes(json.dumps(raw|change).encode())
            with self.assertRaises(ManifestError):
                FlowManifest.from_json_bytes(b'{"schema":1,"schema":1}')

    def test_flow_conflicting_writers_preserve_one_complete_release(self):
        with workspace() as tmp:
            root=Path(tmp); first=self._flow_candidate(root/'one'); second=self._flow_candidate(root/'two',value=2)
            store=LocalStore(root/'store')
            def attempt(ref):
                try: return publish_flow(ref,store=store)
                except StoreError: return None
            with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(attempt,(first,second)))
            self.assertEqual(sum(x is not None for x in outcomes),1)
            ref=FlowStore(store).resolve('boundary.flow','1')
            self.assertEqual(len(list(ref.root.iterdir())),2)
            self.assertTrue(first.root.exists() and second.root.exists())

    def test_task_discovery_ignores_in_progress_copy(self):
        with workspace() as tmp:
            root=Path(tmp); store=LocalStore(root/'store')
            private=store.root/'boundary.pending'/'1.0.0'/'.cpython-312.publishing-1'
            private.parent.mkdir(parents=True)
            stage(private,task_id='boundary.pending')
            self.assertEqual(list(store.list()),[])
            with self.assertRaises(StoreError): store.resolve('boundary.pending','1.0.0')

    def test_flow_copy_corruption_and_symlink_destination_do_not_publish(self):
        with workspace() as tmp:
            root=Path(tmp); candidate=self._flow_candidate(root/'candidate'); store=LocalStore(root/'store')
            original=shutil.copyfile
            def corrupt(src,dst):
                result=original(src,dst)
                if Path(dst).suffix=='.py': Path(dst).write_text('corrupt')
                return result
            with patch('weavem.flows.shutil.copyfile',side_effect=corrupt):
                with self.assertRaises(IntegrityError): publish_flow(candidate,store=store)
            self.assertEqual(FlowStore(store).list(),())
            outside=root/'outside'; outside.mkdir()
            shutil.rmtree(store.root/'_flows')
            (store.root/'_flows').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(IntegrityError): publish_flow(candidate,store=store)
            self.assertEqual(list(outside.iterdir()),[])

    def test_flow_info_remains_metadata_only_and_rejects_unsafe_ids(self):
        with workspace() as tmp:
            root=self._project(Path(tmp)/'project')
            ref=publish_flow(self._flow_candidate(Path(tmp)/'candidate'),project=root)
            manifest=FlowManifest.from_json_bytes(ref.manifest_path.read_bytes())
            (ref.root/manifest.artifact_name).write_text('raise RuntimeError("do not execute")')
            self.assertEqual(self._cli(root,'flow','info','boundary.flow==1','--json'),0)
            with self.assertRaises(ContractError): FlowStore(root/'task-store').resolve('../escape','1')


if __name__=='__main__': unittest.main()
