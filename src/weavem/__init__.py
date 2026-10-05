"""Weavem task framework public API."""
from .runtime import task

def flow(*args, **kwargs):
    """Lazily forward to Prefect's real flow decorator without changing settings."""
    from prefect import flow as prefect_flow
    return prefect_flow(*args, **kwargs)

__all__ = ["flow", "task"]
