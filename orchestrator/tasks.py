"""
orchestrator/tasks.py
----------------------
Re-exports from task_decomposer for backward compatibility.
"""
from orchestrator.task_decomposer import (
    decompose_with_fallback,
    topological_sort,
    TaskSpec,
)

__all__ = ["decompose_with_fallback", "topological_sort", "TaskSpec"]