"""Maintainer-only header-pack preparation; run with the target interpreter.

All inputs must be obtained and checksum-verified from the documented upstream
release first. This script never downloads, configures, or invents Python headers.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import sysconfig
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--include', type=Path, required=True)
parser.add_argument('--pyconfig', type=Path, required=True)
parser.add_argument('--license', type=Path, required=True)
parser.add_argument('--upstream-archive', type=Path, required=True)
parser.add_argument('--upstream-sha256', required=True)
parser.add_argument('--upstream-url', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if hashlib.sha256(args.upstream_archive.read_bytes()).hexdigest() != args.upstream_sha256:
    raise RuntimeError('Upstream archive checksum mismatch; header pack not generated')
if not (args.include / 'Python.h').is_file() or not args.pyconfig.is_file():
    raise RuntimeError('The verified interpreter header set is incomplete')
license_text = args.license.read_bytes()
with args.pyconfig.open() as handle:
    keys = sysconfig.parse_config_h(handle)
config = sysconfig.get_config_vars()
identity = f'cpython-{sys.version_info.major}{sys.version_info.minor}-{sys.version_info.micro}-linux-x86_64'
args.output.mkdir(parents=True, exist_ok=True)
stream = io.BytesIO()
with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as zipped:
    with tarfile.open(fileobj=zipped, mode='w') as archive:
        for source in sorted(args.include.rglob('*.h')):
            relative = source.relative_to(args.include).as_posix()
            data = (args.pyconfig if relative == 'pyconfig.h' else source).read_bytes()
            member = tarfile.TarInfo(relative)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
data = stream.getvalue()
name = identity + '.tar.gz'
(args.output / name).write_bytes(data)
(args.output / (identity + '-LICENSE.txt')).write_bytes(license_text)
record = dict(version=list(sys.version_info[:3]), minor=list(sys.version_info[:2]),
              soabi=config['SOABI'], config={k: config.get(k) for k in sorted(keys)},
              archive=name, sha256=hashlib.sha256(data).hexdigest(),
              upstream_url=args.upstream_url, upstream_sha256=args.upstream_sha256,
              normalization='Header contents unchanged; pyconfig.h selected for Linux x86_64; archive metadata normalized.')
(args.output / (identity + '.json')).write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
print(identity, len(data), record['sha256'])
