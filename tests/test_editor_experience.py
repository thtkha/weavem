"""Saved mapped flows and shared structured results remain ordinary Python."""
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest

from _support import workspace
from weavem.editor_flows import save_flow
from weavem.editor_graph import editor_catalog
from weavem.editor_worker import _run_saved_flow
from weavem.flows import load_local_flow


class EditorExperienceTests(unittest.TestCase):
    def test_nested_field_mapping_matches_saved_python_and_worker(self):
        with workspace('experience-mapping-') as raw:
            root = Path(raw)
            (root / 'weavem.toml').write_text('[tasks.source]\npath="tasks/source"\n[tasks.target]\npath="tasks/target"\n')
            for alias, source in [('source', 'def run(): return {"customers": [{"email": "alice@example.com"}]}\n'),
                                  ('target', 'def run(to): return "sent:" + to\n')]:
                directory = root / 'tasks' / alias
                directory.mkdir(parents=True)
                (directory / 'task.toml').write_text(f'[task]\ntask_id="experience.{alias}"\nversion="1.0.0"\nbackend="{"cython" if alias == "target" else "python"}"\n')
                (directory / 'implementation.py').write_text(source)
            keys = {alias: key for key, alias in editor_catalog(root)['bindings'].items()}
            graph = {'kind': 'weavem.graph', 'schema': 2, 'name': 'mapped', 'nodes': [
                {'id': 'fetch', 'taskKey': keys['source'], 'parameters': {}},
                {'id': 'send', 'taskKey': keys['target'], 'parameters': {}}],
                'edges': [{'id': 'mapping', 'source': 'fetch', 'target': 'send', 'argument': 'to', 'sourcePath': ['customers', 0, 'email']}]}
            saved = save_flow('mapped', graph, None, None, root)
            self.assertEqual(graph, saved['graph'])
            expected = {'send': 'sent:alice@example.com'}
            self.assertEqual(expected, load_local_flow('mapped', project=root)())
            env = dict(os.environ); env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
            cli = subprocess.run([sys.executable, '-m', 'weavem', '--project', str(root), 'flow', 'run', 'mapped'], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(0, cli.returncode, cli.stderr)
            self.assertEqual(expected, json.loads(cli.stdout.strip().splitlines()[-1]))
            events = []
            self.assertEqual(expected, _run_saved_flow({'project': str(root), 'flowName': 'mapped', 'revision': saved['revision'], 'params': {}}, events.append))
            self.assertEqual(expected, events[-1]['resultValue']['value'])
            self.assertTrue(any(e.get('nodeId') == 'fetch' and e.get('value', {}).get('kind') == 'json' for e in events))
