"""Data-only authored-flow location resolution shared by every authoring surface."""
from pathlib import Path
from .contracts import ContractError


def flow_directories(config):
    roots = config.flow_paths or (config.root / 'flows',)
    for root in roots:
        if any(p.is_symlink() for p in (root, *root.parents)) or (root.exists() and not root.is_dir()):
            raise ContractError(f'flows must be regular project directories: {root}')
    return roots


def flow_definitions(config):
    result = {}
    for root in flow_directories(config):
        for path in sorted(root.glob('*.toml')):
            if path.stem in result:
                raise ContractError(f'ambiguous local flow {path.stem}: {result[path.stem]} and {path}')
            result[path.stem] = path
    return result


def flow_metadata_path(config, name):
    return flow_definitions(config).get(name, flow_directories(config)[0] / f'{name}.toml')
