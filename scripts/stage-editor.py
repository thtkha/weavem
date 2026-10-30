#!/usr/bin/env python3
"""Maintainer-only: build and stage the production UI before Python packaging."""
from pathlib import Path
import argparse
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--skip-build', action='store_true', help='Stage an already verified ui/dist build')
args = parser.parse_args()
if not args.skip_build:
    subprocess.run(['npm', 'run', 'build'], cwd=root / 'ui', check=True)
source = root / 'ui/dist'
if not (source / 'index.html').is_file() or not (source / 'assets').is_dir():
    raise SystemExit('Missing production UI: run npm ci --prefix ui, then this script.')
destination = root / 'src/weavem/_ui'
if destination.exists():
    shutil.rmtree(destination)
destination.mkdir()
shutil.copyfile(source / 'index.html', destination / 'index.html')
for path in (source / 'assets').rglob('*'):
    if path.is_symlink():
        raise SystemExit(f'Refusing symlinked UI asset: {path}')
    if path.is_file() and path.suffix != '.map':
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
print(f'Staged production editor: {destination}')
