"""
database/crud.py
----------------
All database read/write operations.  Every function takes an open Session
and is side-effect-free beyond the DB — callers own commit/rollback.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import bcrypt

from .models import User, Project, Task
from utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def create_user(db: Session, email: str, password: str) -> dict | None:
    """
    Returns {"id": int, "email": str} on success, None if email already exists.
    Does NOT commit — caller is responsible.
    """
    if get_user_by_email(db, email):
        return None
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(email=email.lower().strip(), hashed_password=hashed)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return {"id": user.id, "email": user.email}


def authenticate_user(db: Session, email: str, password: str) -> dict | None:
    """Returns {"id": int, "email": str} on success, None on failure."""
    user = get_user_by_email(db, email)
    if user and bcrypt.checkpw(password.encode("utf-8"), user.hashed_password.encode("utf-8")):
        return {"id": user.id, "email": user.email}
    return None


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────

def create_project(db: Session, user_id: int, name: str, goal: str) -> Project:
    project = Project(
        user_id=user_id,
        name=name.strip(),
        goal=goal.strip(),
        current_stage="idea",
        status="active",
        progress=0,
    )
    db.add(project)
    db.flush()
    return project


def get_projects_by_user(db: Session, user_id: int) -> list[Project]:
    return (
        db.query(Project)
        .filter(Project.user_id == user_id)
        .order_by(Project.created_at.desc())
        .all()
    )


def get_project(db: Session, project_id: int, user_id: int | None = None) -> Project | None:
    q = db.query(Project).filter(Project.id == project_id)
    if user_id is not None:       # explicit None check — not falsy check
        q = q.filter(Project.user_id == user_id)
    return q.first()


def update_project_stage(db: Session, project_id: int, stage: str) -> Project | None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.current_stage = stage
        project.updated_at = datetime.utcnow()
        db.flush()
    return project


def update_project_status(db: Session, project_id: int, status: str) -> Project | None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.status = status
        project.updated_at = datetime.utcnow()
        db.flush()
    return project


def update_project_progress(db: Session, project_id: int) -> int:
    """Recalculates progress from tasks and persists it.  Returns new value."""
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    total     = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    progress  = int((completed / total) * 100) if total > 0 else 0

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.progress   = progress
        project.updated_at = datetime.utcnow()
        db.flush()
    return progress


def delete_project(db: Session, project_id: int) -> bool:
    """Cascade handled by SQLAlchemy relationship.  Returns True if deleted."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False
    db.delete(project)
    db.flush()
    return True


# ─────────────────────────────────────────────
# Task
# ─────────────────────────────────────────────

_ALLOWED_TASK_FIELDS = {
    "stage", "task_id", "description", "assigned_agent",
    "dependencies", "risk", "status", "requires_approval",
}


def create_task(db: Session, project_id: int, task_data: dict) -> Task:
    """
    Explicit field whitelist prevents arbitrary columns being injected
    via **task_data.
    """
    safe = {k: v for k, v in task_data.items() if k in _ALLOWED_TASK_FIELDS}
    task = Task(project_id=project_id, **safe)
    db.add(task)
    db.flush()
    return task


def get_tasks_for_project(db: Session, project_id: int) -> list[Task]:
    return (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.created_at)
        .all()
    )


def get_tasks_for_stage(db: Session, project_id: int, stage: str) -> list[Task]:
    """Return only the tasks belonging to a specific stage."""
    return (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.stage == stage)
        .order_by(Task.created_at)
        .all()
    )


def update_task_status(
    db: Session,
    task_db_id: int,
    status: str,
    result: str | None = None,
) -> Task | None:
    task = db.query(Task).filter(Task.id == task_db_id).first()
    if not task:
        return None
    task.status = status
    if result is not None:
        task.result = result
    if status == "completed":
        task.completed_at = datetime.utcnow()
    db.flush()
    return task


def approve_task(db: Session, task_db_id: int) -> Task | None:
    """Move a 'awaiting_approval' task back to 'pending' so it can execute."""
    task = db.query(Task).filter(Task.id == task_db_id).first()
    if task and task.status == "awaiting_approval":
        task.status           = "pending"
        task.requires_approval = "false"
        db.flush()
    return task