import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG (MUST COME FIRST)
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PMS Dashboard – Averra",
    page_icon="📈",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# 🔐 PASSWORD PROTECTION
# ─────────────────────────────────────────────────────────────
PASSWORD = "Averra3469"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    password = st.text_input("🔐 Enter Password", type="password")

    if password == PASSWORD:
        st.session_state["authenticated"] = True
    elif password:
        st.error("❌ Incorrect password")

    return st.session_state["authenticated"]

if not check_password():
    st.stop()

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
