import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import time
from datetime import datetime

# 🔐 PASSWORD PROTECTION
PASSWORD = "Averra3469"

def check_password():
    def password_entered():
        if st.session_state["password"] == PASSWORD:
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("🔐 Enter Password", type="password", key="password", on_change=password_entered)
        return False
    elif not st.session_state["authenticated"]:
        st.text_input("🔐 Enter Password", type="password", key="password", on_change=password_entered)
        st.error("❌ Incorrect password")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PMS Dashboard – Averra",
    page_icon="📈",
    layout="wide",
)

st.title("📈 PMS Portfolio Dashboard")
st.caption("Averra Asset Managers LLP")

# ─────────────────────────────────────────────────────────────
# LOAD EXCEL (AUTO)
# ─────────────────────────────────────────────────────────────
import os, glob

script_dir = os.path.dirname(os.path.abspath(__file__))
excel_files = sorted(
    glob.glob(os.path.join(script_dir, "*.xlsx")),
    key=os.path.getmtime,
    reverse=True,
)

if not excel_files:
    st.error("❌ No Excel file found in folder")
    st.stop()

file_path = excel_files[0]

df = pd.read_excel(file_path)

st.success(f"Loaded: {os.path.basename(file_path)}")

# ─────────────────────────────────────────────────────────────
# SIMPLE DISPLAY
# ─────────────────────────────────────────────────────────────
st.subheader("Preview Data")
st.dataframe(df.head())

# ─────────────────────────────────────────────────────────────
# SAMPLE METRIC
# ─────────────────────────────────────────────────────────────
st.metric("Rows Loaded", len(df))
