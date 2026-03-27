import streamlit as st
from database.db import SessionLocal
from database import crud

def project_card(project):
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {project.name}")
            st.caption(f"**Stage:** {project.current_stage} · **Status:** {project.status}")
            st.progress(project.progress / 100, text=f"Progress {project.progress}%")
            st.write(f"**Goal:** {project.goal[:150]}{'...' if len(project.goal) > 150 else ''}")
        with col2:
            if st.button("View", key=f"view_{project.id}"):
                st.session_state.selected_project_id = project.id
                st.switch_page("pages/project.py")
            if st.button("Delete", key=f"delete_{project.id}"):
                db = SessionLocal()
                crud.delete_project(db, project.id)
                db.close()
                st.rerun()