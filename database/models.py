from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, JSON, Index
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)

    projects = relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Project(Base):
    __tablename__ = "projects"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(200), nullable=False)
    goal          = Column(Text, nullable=False)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_stage = Column(String(50), default="idea", nullable=False)
    status        = Column(String(20), default="active", nullable=False)
    progress      = Column(Integer, default=0, nullable=False)
    

    owner = relationship("User", back_populates="projects")
    tasks = relationship(
        "Task",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Task.created_at",
    )

    __table_args__ = (
        Index("ix_projects_user_id", "user_id"),
        Index("ix_projects_status",  "status"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id             = Column(Integer, primary_key=True, index=True)
    project_id     = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stage          = Column(String(50), nullable=False, default="idea")
    task_id        = Column(String(100), nullable=False)
    description    = Column(Text, nullable=False)
    assigned_agent = Column(String(50), nullable=False)
    # Store as JSON list of task_id strings
    dependencies   = Column(JSON, nullable=False, default=lambda: [])
    risk           = Column(String(20), nullable=False, default="low")
    status         = Column(String(20), nullable=False, default="pending")
    # True when risk=high/critical and waiting on founder approval
    requires_approval = Column(String(5), nullable=False, default="false")
    result         = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    completed_at   = Column(DateTime, nullable=True)
    # In Task class, add:
    retry_count = Column(Integer, default=0, nullable=False)
    last_error  = Column(Text, nullable=True)

    project = relationship("Project", back_populates="tasks")

    __table_args__ = (
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_stage",      "stage"),
        Index("ix_tasks_status",     "status"),
    )