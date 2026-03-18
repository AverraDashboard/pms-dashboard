# (Your full app code with password protection added)

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import time
from datetime import datetime

# PASSWORD PROTECTION
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

# Simple test app (rest of your code remains same)
st.title("📈 PMS Dashboard – Averra")
st.write("App is secured with password")
