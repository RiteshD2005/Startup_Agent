"""
utils/artifact_store.py
------------------------
Saves and retrieves agent-generated artifacts (reports, contracts, code)
per project.  Each artifact gets a JSON metadata sidecar file.

Directory layout:
    data/artifacts/
    └── {project_id}/
        ├── {task_id}_20240101_120000.md
        ├── {task_id}_20240101_120000.meta.json
        └── ...

Usage:
    from utils.artifact_store import save_artifact, list_artifacts, read_artifact

    path = save_artifact(project_id=1, task_id="market_research",
                         content="# Report\n...", extension="md")
    artifacts = list_artifacts(project_id=1)
    text = read_artifact(project_id=1, filename=artifacts[0]["filename"])
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)


def _project_dir(project_id: int) -> Path:
    config = get_config()
    path   = Path(config["ARTIFACT_DIR"]) / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_artifact(
    project_id: int,
    task_id:    str,
    content:    str,
    extension:  str = "txt",
    agent:      str = "",
    stage:      str = "",
    filename:   Optional[str] = None,
) -> str:
    """
    Write content to disk and return the absolute file path.

    Args:
        project_id: DB project id — used as the directory name.
        task_id:    The task's snake_case id — used in the filename.
        content:    The text to save.
        extension:  File extension without dot (txt, md, py, json).
        agent:      Agent name for the metadata sidecar.
        stage:      Startup stage for the metadata sidecar.
        filename:   Override the auto-generated filename.

    Returns:
        Absolute path to the saved file as a string.
    """
    dir_path  = _project_dir(project_id)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if filename is None:
        filename = f"{task_id}_{timestamp}.{extension}"

    file_path = dir_path / filename
    file_path.write_text(content, encoding="utf-8")

    # Write a JSON sidecar with metadata
    meta = {
        "project_id":  project_id,
        "task_id":     task_id,
        "agent":       agent,
        "stage":       stage,
        "created_at":  datetime.utcnow().isoformat(),
        "filename":    filename,
        "size_bytes":  len(content.encode("utf-8")),
    }
    meta_path = dir_path / f"{filename}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    logger.info(
        "Artifact saved: project=%d task='%s' file=%s (%d bytes)",
        project_id, task_id, filename, meta["size_bytes"]
    )
    return str(file_path)


def list_artifacts(project_id: int) -> list[dict]:
    """
    Returns a list of artifact metadata dicts for the project,
    sorted newest first.  Skips .meta.json sidecar files.
    """
    dir_path = _project_dir(project_id)
    artifacts = []

    for meta_path in sorted(dir_path.glob("*.meta.json"), reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            artifacts.append(meta)
        except Exception as exc:
            logger.warning("Could not read artifact metadata %s: %s", meta_path, exc)

    return artifacts


def read_artifact(project_id: int, filename: str) -> str:
    """
    Read and return the text content of an artifact.

    Raises:
        FileNotFoundError: if the artifact does not exist.
    """
    file_path = _project_dir(project_id) / filename
    if not file_path.exists():
        raise FileNotFoundError(
            f"Artifact '{filename}' not found for project {project_id}"
        )
    return file_path.read_text(encoding="utf-8")


def delete_artifact(project_id: int, filename: str) -> bool:
    """Delete an artifact and its sidecar. Returns True if deleted."""
    dir_path  = _project_dir(project_id)
    file_path = dir_path / filename
    meta_path = dir_path / f"{filename}.meta.json"
    deleted   = False
    for p in (file_path, meta_path):
        if p.exists():
            p.unlink()
            deleted = True
    return deleted