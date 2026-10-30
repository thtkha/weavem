#!/usr/bin/env python3
"""Check production UI contents match across wheel, sdist and rebuilt wheel."""
import argparse
from pathlib import Path
import tarfile
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--wheel',type=Path,required=True)
p.add_argument('--sdist',type=Path,required=True)
p.add_argument('--rebuilt-wheel',type=Path)
a=p.parse_args()
def wheel(path):
    with zipfile.ZipFile(path) as z:
        return {n.split('weavem/_ui/',1)[1]:z.read(n) for n in z.namelist() if 'weavem/_ui/' in n and not n.endswith('/')}
def source(path):
    with tarfile.open(path) as t:
        return {m.name.split('src/weavem/_ui/',1)[1]:t.extractfile(m).read() for m in t.getmembers() if 'src/weavem/_ui/' in m.name and m.isfile()}
x=wheel(a.wheel)
assert 'index.html' in x and any(n.endswith('.js') for n in x), 'Missing editor assets'
assert not any(n.endswith('.map') or 'node_modules' in n for n in x), 'Development assets shipped'
assert source(a.sdist)==x,'sdist UI differs from wheel'
if a.rebuilt_wheel:assert wheel(a.rebuilt_wheel)==x,'Rebuilt wheel UI differs'
print(f'PASS: {len(x)} identical production assets; no source maps or node_modules')
