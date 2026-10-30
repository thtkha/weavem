#!/usr/bin/env python3
"""Verify packaged editor outside checkout with no Node or inherited PYTHONPATH."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work-dir', type=Path, required=True)
args = parser.parse_args()
root = args.work_dir.resolve()
root.mkdir(parents=True, exist_ok=False)
import weavem
assert Path(weavem.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), 'Weavem was imported from outside the consumer environment'
project = root / 'project'
project.mkdir()
(project / 'weavem.toml').write_text('[weavem]\n[tasks.identity]\npath="tasks/identity"\n')
task = project / 'tasks/identity'
task.mkdir(parents=True)
(task / 'task.toml').write_text('[task]\ntask_id="editor.identity"\nversion="1.0.0"\nbackend="python"\nsource="implementation.py"\nexport="run"\n')
(task / 'implementation.py').write_text('def run():\n import sys\n return sys.executable\n')
env = {k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'} and not k.startswith('PREFECT_')}
empty = root / 'empty-path'
empty.mkdir()
env.update(PATH=str(empty), PREFECT_HOME=str(root / 'prefect'), PREFECT_SERVER_ANALYTICS_ENABLED='false', PREFECT_LOGGING_LEVEL='WARNING')
os.environ.update(env)
log = (root / 'server.log').open('w+')
process = subprocess.Popen([sys.executable,'-I','-m','weavem','editor','--project',str(project),'--port','0'],cwd=root,env=env,stdout=log,stderr=log,text=True)
try:
    url = None
    for _ in range(100):
        log.flush()
        match = re.search(r'Weavem editor: (http://127\.0\.0\.1:\d+)', (root/'server.log').read_text())
        if match: url=match.group(1); break
        if process.poll() is not None: raise RuntimeError((root/'server.log').read_text())
        time.sleep(.1)
    assert url, 'editor did not start'
    def request(path, payload=None, token=None):
        headers = {'X-Weavem-Token':token} if token else {}
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None: headers['Content-Type']='application/json'
        with urllib.request.urlopen(urllib.request.Request(url+path,data=data,headers=headers),timeout=30) as response:
            return response.read(), response.headers.get_content_type()
    page,_=request('/')
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"',page.decode())
    assert assets, 'no packaged assets referenced'
    for asset in assets:
        content,mime=request(asset)
        assert content and (mime in {'text/javascript','application/javascript','text/css'}), (asset,mime)
    session=json.loads(request('/api/session')[0]);token=session['token']
    assert session['environment']=={'pythonExecutable':sys.executable,'pythonVersion':__import__('platform').python_version(),'weavemVersion':importlib.metadata.version('weavem')}
    key='local:'+str((task/'task.toml').resolve())
    graph={'kind':'weavem.graph','schema':1,'name':'installed_identity','nodes':[{'id':'identity','taskKey':key,'parameters':{}}],'edges':[]}
    saved=json.loads(request('/api/flows/installed_identity',{'graph':graph,'layout':None,'expectedRevision':None},token)[0])
    listed=json.loads(request('/api/flows',token=token)[0])
    assert any(item['name']=='installed_identity' for item in listed['flows']), listed
    assert (project/'flows/installed_identity.py').is_file()
    state=json.loads(request('/api/runs',{'flowName':'installed_identity','revision':saved['revision'],'params':{}},token)[0])
    for _ in range(240):
        state=json.loads(request('/api/runs/'+state['runId'],token=token)[0])
        if state['status']!='running':break
        time.sleep(.5)
    assert state['status']=='completed',state
    assert sys.executable in state['result'], state
    from weavem.flows import load_local_flow
    assert load_local_flow('installed_identity',project=project)()=={'identity':sys.executable}
    cli=subprocess.run([sys.executable,'-I','-m','weavem','--project',str(project),'flow','run','installed_identity'],env=env,cwd=root,text=True,capture_output=True,timeout=180)
    assert cli.returncode==0,cli.stderr
    assert json.loads(cli.stdout.strip().splitlines()[-1])=={'identity':sys.executable}
    result={'status':'passed','assets':assets,'environment':session['environment'],'nodeAvailable':False,'workerIdentity':sys.executable,'editorApiCliPythonParity':True}
    (root/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
finally:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
    log.close()
