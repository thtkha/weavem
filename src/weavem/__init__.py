"""Weavem task framework public API."""
from .runtime import task
from .project import Project
from .errors import TaskError


def load_flow(flow_id, version, **options):
    """Load an exact released flow, with its published task dependencies pinned."""
    from .flows import load_flow as load_released_flow
    return load_released_flow(flow_id, version, **options)

def flow(*args, **kwargs):
    """Lazily forward to Prefect's real flow decorator without changing settings."""
    from prefect import flow as prefect_flow
    return prefect_flow(*args, **kwargs)

__all__ = ["flow", "task", "load_flow", "Project", "TaskError"]
