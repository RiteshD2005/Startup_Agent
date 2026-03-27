"""
pages/agents.py
----------------
Agent overview — all five specialist agents as cards with task stats.
Clicking a card shows every task that agent has worked on.
"""

import streamlit as st
from database.db import SessionLocal
from database import crud

AGENTS = {
    "strategy": {
        "name":        "Strategy Agent",
        "icon":        "📊",
        "description": "Market research, competitor analysis, OKRs, go-to-market planning.",
    },
    "marketing": {
        "name":        "Marketing Agent",
        "icon":        "📢",
        "description": "Campaign strategy, ad copy, SEO, content, social media, email.",
    },
    "legal": {
        "name":        "Legal Agent",
        "icon":        "⚖️",
        "description": "Contracts, compliance, IP, ToS, privacy, entity formation.",
    },
    "engineering": {
        "name":        "Engineering Agent",
        "icon":        "💻",
        "description": "Architecture, code scaffolds, database design, API, DevOps.",
    },
    "finance": {
        "name":        "Finance Agent",
        "icon":        "💰",
        "description": "Runway, burn rate, pricing, fundraising, cap table.",
    },
}


def show_agents():
    project_id = st.session_state.get("selected_project_id")
    if not project_id:
        st.warning("No project selected. Go to the Dashboard and open a project first.")
        return

    selected = st.session_state.get("selected_agent")
    if selected:
        _show_detail(project_id, selected)
    else:
        _show_cards(project_id)


def _show_cards(project_id: int):
    st.title("Specialist agents")

    db = SessionLocal()
    try:
        all_tasks = crud.get_tasks_for_project(db, project_id)
    finally:
        db.close()

    agent_tasks: dict[str, list] = {k: [] for k in AGENTS}
    for t in all_tasks:
        if t.assigned_agent in agent_tasks:
            agent_tasks[t.assigned_agent].append(t)

    cols = st.columns(2)
    for idx, (key, meta) in enumerate(AGENTS.items()):
        with cols[idx % 2]:
            tasks     = agent_tasks[key]
            total     = len(tasks)
            completed = sum(1 for t in tasks if t.status == "completed")
            progress  = int((completed / total) * 100) if total > 0 else 0

            with st.container(border=True):
                st.markdown(f"### {meta['icon']} {meta['name']}")
                st.caption(meta["description"])

                c1, c2 = st.columns(2)
                c1.metric("Assigned", total)
                c2.metric("Completed", completed)

                st.progress(progress / 100, text=f"{progress}% done")

                if st.button("View tasks", key=f"view_{key}", use_container_width=True):
                    st.session_state.selected_agent = key
                    st.rerun()


def _show_detail(project_id: int, agent_key: str):
    meta = AGENTS[agent_key]
    st.title(f"{meta['icon']} {meta['name']}")
    st.caption(meta["description"])

    if st.button("← Back to agents"):
        st.session_state.selected_agent = None
        st.rerun()

    st.divider()

    db = SessionLocal()
    try:
        all_tasks   = crud.get_tasks_for_project(db, project_id)
        agent_tasks = [t for t in all_tasks if t.assigned_agent == agent_key]
    finally:
        db.close()

    if not agent_tasks:
        st.info("No tasks have been assigned to this agent yet.")
        return

    _STATUS_ICON = {
        "pending": "🔵", "in_progress": "🟡", "completed": "🟢",
        "failed": "🔴", "blocked": "⛔", "awaiting_approval": "🟠",
    }

    st.subheader(f"Tasks ({len(agent_tasks)})")
    for task in agent_tasks:
        icon = _STATUS_ICON.get(task.status, "⚪")
        with st.expander(f"{icon} `{task.task_id}` — {task.description[:80]}"):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Status:** `{task.status}`")
            c2.markdown(f"**Risk:** {task.risk}")
            c3.markdown(f"**Stage:** {task.stage}")
            if task.dependencies:
                st.markdown(f"**Depends on:** {', '.join(task.dependencies)}")
            if task.result:
                st.markdown("**Output:**")
                st.text_area("", value=task.result, height=200,
                             key=f"result_{task.id}", disabled=True)


show_agents()