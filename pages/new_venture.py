"""
pages/new_venture.py
---------------------
Multi-step wizard: goal input → optional clarification loop → project creation.
"""

import streamlit as st
from contextlib import contextmanager

from database.db import SessionLocal
from database import crud
from orchestrator.workers import start_orchestration
from utils.clarify import is_goal_clear, generate_clarifying_question, MAX_CLARIFICATIONS


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


# ── Session-state initialiser ─────────────────────────────────────────────

def _init_state():
    defaults = {
        "wiz_state":         "input",     # input | clarify | done
        "wiz_name":          "",
        "wiz_goal":          "",
        "wiz_question":      "",
        "wiz_clarify_count": 0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _reset_state():
    for key in ("wiz_state", "wiz_name", "wiz_goal",
                "wiz_question", "wiz_clarify_count"):
        st.session_state.pop(key, None)


# ── Page ──────────────────────────────────────────────────────────────────

def show_new_venture():
    st.title("Create a New Venture")
    _init_state()

    # ── Stage 1: Initial input ─────────────────────────────────────────────
    if st.session_state.wiz_state == "input":
        with st.form("venture_input_form"):
            name = st.text_input(
                "Venture name",
                placeholder="e.g. AI-powered recruiting tool",
            )
            goal = st.text_area(
                "Describe your idea",
                height=140,
                placeholder=(
                    "e.g. Build a platform that uses AI to match job seekers "
                    "with employers based on skills, not just keywords."
                ),
            )
            submitted = st.form_submit_button("Next →", use_container_width=True)

        if submitted:
            name = name.strip()
            goal = goal.strip()
            if not name or not goal:
                st.error("Please fill in both fields before continuing.")
                return

            st.session_state.wiz_name = name
            st.session_state.wiz_goal = goal

            with st.spinner("Analysing your goal…"):
                clear = is_goal_clear(goal)

            if clear:
                st.session_state.wiz_state = "done"
            else:
                with st.spinner("Generating a clarifying question…"):
                    st.session_state.wiz_question = generate_clarifying_question(goal)
                st.session_state.wiz_state = "clarify"
            st.rerun()

    # ── Stage 2: Clarification loop ────────────────────────────────────────
    elif st.session_state.wiz_state == "clarify":
        clarify_count = st.session_state.wiz_clarify_count

        st.subheader("Let's sharpen your idea")

        # Progress indicator
        remaining = MAX_CLARIFICATIONS - clarify_count
        st.caption(
            f"Question {clarify_count + 1} of {MAX_CLARIFICATIONS}"
            if remaining > 0 else "Last clarification"
        )

        with st.container(border=True):
            st.markdown(f"**Your goal so far:**")
            st.write(st.session_state.wiz_goal)

        st.markdown(f"**{st.session_state.wiz_question}**")
        answer = st.text_area(
            "Your answer",
            placeholder="Type your response here…",
            key=f"clarify_answer_{clarify_count}",
        )

        col_submit, col_skip = st.columns([3, 1])

        with col_submit:
            if st.button("Submit Answer", use_container_width=True):
                if not answer.strip():
                    st.error("Please provide an answer, or skip.")
                    return

                # Append detail to goal
                st.session_state.wiz_goal = (
                    f"{st.session_state.wiz_goal}\n"
                    f"(Additional detail: {answer.strip()})"
                )
                st.session_state.wiz_clarify_count += 1

                # Check if we've hit the max
                if st.session_state.wiz_clarify_count >= MAX_CLARIFICATIONS:
                    st.session_state.wiz_state = "done"
                    st.rerun()
                    return

                with st.spinner("Checking clarity…"):
                    clear = is_goal_clear(st.session_state.wiz_goal)

                if clear:
                    st.session_state.wiz_state = "done"
                else:
                    with st.spinner("Next question…"):
                        st.session_state.wiz_question = generate_clarifying_question(
                            st.session_state.wiz_goal
                        )
                st.rerun()

        with col_skip:
            if st.button("Skip", use_container_width=True):
                st.session_state.wiz_state = "done"
                st.rerun()

    # ── Stage 3: Create project ────────────────────────────────────────────
    elif st.session_state.wiz_state == "done":
        st.subheader("Ready to launch")

        with st.container(border=True):
            st.markdown(f"**Venture:** {st.session_state.wiz_name}")
            st.markdown("**Refined goal:**")
            st.write(st.session_state.wiz_goal)

        if st.button("Create venture & start agents", use_container_width=True, type="primary"):
            project_id = None
            try:
                with get_db() as db:
                    project = crud.create_project(
                        db,
                        st.session_state.user_id,
                        st.session_state.wiz_name,
                        st.session_state.wiz_goal,
                    )
                    project_id = project.id   # capture before db closes

                # Start orchestration AFTER db session is fully closed
                start_orchestration(project_id)

                st.success(
                    f"Venture **{st.session_state.wiz_name}** created! "
                    "Agents are now working in the background."
                )

                # Clean up wizard state, then navigate
                _reset_state()
                st.session_state.selected_project_id = project_id
                st.switch_page("pages/project.py")

            except Exception as exc:
                st.error(f"Failed to create venture: {exc}")


show_new_venture()