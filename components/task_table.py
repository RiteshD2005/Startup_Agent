import streamlit as st
import pandas as pd

def task_table(tasks):
    data = []
    for t in tasks:
        data.append({
            "ID": t.task_id,
            "Description": t.description,
            "Agent": t.assigned_agent,
            "Risk": t.risk,
            "Status": t.status,
            "Result": t.result[:80] + "..." if t.result and len(t.result) > 80 else t.result
        })
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)   # Use width='stretch' if needed