"""
pages/dashboard.py
-------------------
Home screen -- lists all ventures with live status and progress bars.
"""

import streamlit as st
from database.db import SessionLocal
from database import crud
from orchestrator.workers import is_running

_STATUS_ICON = {
    "active":    "🟡",
    "completed": "🟢",
    "paused":    "⏸",
    "failed":    "🔴",
}

_STAGE_ORDER = ["idea", "validation", "build", "gtm", "scale"]


def show_dashboard():
    st.title("My ventures")

    db = SessionLocal()
    try:
        projects = crud.get_projects_by_user(db, st.session_state.user_id)
    finally:
        db.close()

    if not projects:
        st.info("No ventures yet. Click **New Venture** in the sidebar to get started.")
        return

    active    = sum(1 for p in projects if p.status == "active")
    completed = sum(1 for p in projects if p.status == "completed")
    running   = sum(1 for p in projects if is_running(p.id))

    c1, c2, c3 = st.columns(3)
    c1.metric("Total ventures", len(projects))
    c2.metric("Active",         active)
    c3.metric("Agents running", running)

    st.divider()

    for project in projects:
        icon     = _STATUS_ICON.get(project.status, "⚪")
        live     = is_running(project.id)
        progress = project.progress or 0

        stage_idx  = (_STAGE_ORDER.index(project.current_stage)
                      if project.current_stage in _STAGE_ORDER else 0)
        stage_dots = "".join("●" if i <= stage_idx else "○"
                             for i in range(len(_STAGE_ORDER)))

        with st.container(border=True):
            col_info, col_btn = st.columns([5, 1])

            with col_info:
                heading = f"{icon} {project.name}"
                if live:
                    heading += "  🔄 *agents running*"
                st.markdown(f"### {heading}")
                st.caption(
                    f"Stage: **{project.current_stage.capitalize()}** {stage_dots}  ·  "
                    f"Status: **{project.status.capitalize()}**  ·  "
                    f"Created: {project.created_at.strftime('%d %b %Y')}"
                )
                st.progress(progress / 100, text=f"{progress}% complete")
                preview = project.goal[:160] + "…" if len(project.goal) > 160 else project.goal
                st.caption(preview)

            with col_btn:
                if st.button("Open", key=f"open_{project.id}", use_container_width=True):
                    st.session_state.selected_project_id = project.id
                    st.switch_page("pages/project.py")


show_dashboard()