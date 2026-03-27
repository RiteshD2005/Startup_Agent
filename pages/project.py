"""
pages/project.py
-----------------
Shows a project's live status, stage-scoped task table, and controls.
"""

import time
import streamlit as st
from contextlib import contextmanager

from database.db import SessionLocal
from database import crud
from orchestrator.workers import start_orchestration, is_running


# ── DB helper ─────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Status → colour mapping ───────────────────────────────────────────────

_STATUS_COLOUR = {
    "pending":           "🔵",
    "in_progress":       "🟡",
    "completed":         "🟢",
    "failed":            "🔴",
    "blocked":           "⛔",
    "awaiting_approval": "🟠",
}

_RISK_COLOUR = {
    "low":      ":green[low]",
    "medium":   ":orange[medium]",
    "high":     ":orange[**high**]",
    "critical": ":red[**critical**]",
}


# ── Task table ────────────────────────────────────────────────────────────

def _render_task_table(tasks, project_id: int):
    if not tasks:
        st.info("No tasks for this stage yet — the orchestrator will generate them shortly.")
        return

    for task in tasks:
        icon   = _STATUS_COLOUR.get(task.status, "⚪")
        risk   = _RISK_COLOUR.get(task.risk, task.risk)
        agent  = task.assigned_agent.capitalize()
        deps   = ", ".join(task.dependencies) if task.dependencies else "—"

        with st.expander(f"{icon} `{task.task_id}` — {task.description[:80]}"):
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"**Agent:** {agent}")
            col2.markdown(f"**Risk:** {risk}")
            col3.markdown(f"**Status:** `{task.status}`")

            if deps != "—":
                st.markdown(f"**Depends on:** `{deps}`")

            if task.result:
                st.markdown("**Output:**")
                st.text_area(
                    label="Task Output",
                    value=task.result,
                    height=120,
                    key=f"result_{task.id}",
                    disabled=True,
                )

            # Approval button for high-risk tasks
            if task.status == "awaiting_approval":
                st.warning(
                    "This task is paused because it is high-risk. "
                    "Review the description above and approve if you wish to proceed."
                )
                if st.button(
                    "Approve & execute",
                    key=f"approve_{task.id}",
                    type="primary",
                ):
                    with get_db() as db:
                        crud.approve_task(db, task.id)
                    st.success("Task approved — agents will execute it shortly.")
                    time.sleep(0.5)
                    st.rerun()


# ── Page ──────────────────────────────────────────────────────────────────

def show_project():
    project_id = st.session_state.get("selected_project_id")
    if not project_id:
        st.warning("No project selected. Go to the Dashboard and pick one.")
        return

    with get_db() as db:
        project = crud.get_project(db, project_id, st.session_state.user_id)
        if not project:
            st.error("Project not found or you don't have access.")
            return

        stage_tasks = crud.get_tasks_for_stage(db, project_id, project.current_stage)
        all_tasks   = crud.get_tasks_for_project(db, project_id)

        # Snapshot values while session is open
        snap = {
            "name":    project.name,
            "goal":    project.goal,
            "stage":   project.current_stage,
            "status":  project.status,
            "progress": project.progress,
        }

    # ── Header ────────────────────────────────────────────────────────────
    st.title(snap["name"])

    running = is_running(project_id)
    if running:
        st.caption("🟢 Agents are running")
    elif snap["status"] == "completed":
        st.caption("✅ All stages completed")
    else:
        st.caption("⏸ Agents idle")

    # ── Metrics ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stage",    snap["stage"].capitalize())
    c2.metric("Status",   snap["status"].capitalize())
    c3.metric("Progress", f"{snap['progress']}%")
    c4.metric("Tasks",    len(all_tasks))

    st.progress(snap["progress"] / 100)

    # ── Goal ──────────────────────────────────────────────────────────────
    with st.expander("View full goal"):
        st.write(snap["goal"])

    # ── Task table ────────────────────────────────────────────────────────
    st.subheader(f"Tasks — {snap['stage'].capitalize()} stage")
    _render_task_table(stage_tasks, project_id)

    # ── Controls ──────────────────────────────────────────────────────────
    st.divider()
    col_refresh, col_start, col_delete = st.columns([2, 2, 1])

    with col_refresh:
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    with col_start:
        if not running and snap["status"] == "active":
            if st.button("Resume agents", use_container_width=True, type="primary"):
                start_orchestration(project_id)
                st.success("Agents restarted.")
                time.sleep(0.5)
                st.rerun()

    with col_delete:
        if st.button("Delete", use_container_width=True):
            st.session_state[f"confirm_delete_{project_id}"] = True

    # Separate confirm step avoids the checkbox-inside-button Streamlit bug
    if st.session_state.get(f"confirm_delete_{project_id}"):
        st.warning("This will permanently delete the project and all its tasks.")
        c_yes, c_no = st.columns(2)
        if c_yes.button("Yes, delete", type="primary"):
            with get_db() as db:
                crud.delete_project(db, project_id)
            st.session_state.pop(f"confirm_delete_{project_id}", None)
            st.session_state.selected_project_id = None
            st.success("Project deleted.")
            time.sleep(0.5)
            st.switch_page("pages/dashboard.py")
        if c_no.button("Cancel"):
            st.session_state.pop(f"confirm_delete_{project_id}", None)
            st.rerun()

    # ── Artifacts ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Saved artifacts")
    _render_artifacts(project_id)

    # ── Auto-refresh while agents are running ─────────────────────────────
    if running:
        time.sleep(5)
        st.rerun()


def _render_artifacts(project_id: int):
    """Show all saved artifact files with inline preview and download button."""
    try:
        from utils.artifact_store import list_artifacts, read_artifact
    except ImportError:
        st.caption("Artifact store not available.")
        return

    artifacts = list_artifacts(project_id)

    if not artifacts:
        st.caption(
            "No artifacts yet — agents will save their reports and documents here "
            "as they complete tasks."
        )
        return

    for meta in artifacts:
        filename = meta.get("filename", "unknown")
        agent    = meta.get("agent",    "agent")
        stage    = meta.get("stage",    "")
        size     = meta.get("size_bytes", 0)
        created  = meta.get("created_at", "")[:16].replace("T", " ")

        badge  = f"{agent.capitalize()} agent"
        detail = f"{stage} stage · {size:,} bytes · {created} UTC"

        with st.expander(f"`{filename}` — {badge} · {detail}"):
            try:
                content = read_artifact(project_id, filename)
                st.markdown(content)
                st.download_button(
                    label="Download file",
                    data=content,
                    file_name=filename,
                    mime="text/markdown",
                    key=f"dl_{project_id}_{filename}",
                )
            except FileNotFoundError:
                st.warning("Artifact file not found on disk.")


show_project()