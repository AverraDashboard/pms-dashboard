"""
PMS Portfolio Dashboard  v2
============================
Works with the Nuvama "Statement of Holding" Excel export.

Install:
    pip install streamlit yfinance pandas openpyxl plotly

Run:
    streamlit run pms_dashboard.py
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PMS Dashboard – Averra",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# PASSWORD GATE
# ─────────────────────────────────────────────────────────────
def check_password():
    # Use query params to persist login across refreshes
    # Once logged in, token is stored in URL so F5 doesn't log out
    params = st.query_params

    # Already authenticated via session or URL token
    if st.session_state.get("authenticated") or params.get("auth") == "ok":
        st.session_state["authenticated"] = True
        return True

    st.markdown("""
    <div style="
        max-width: 400px;
        margin: 120px auto;
        padding: 40px;
        background: #0e1a2b;
        border-radius: 16px;
        border: 1px solid #2e3a4a;
        text-align: center;
    ">
        <div style="font-size: 2.5rem; margin-bottom: 8px;">📈</div>
        <div style="font-size: 1.4rem; font-weight: 700; color: #e0e8f0; margin-bottom: 4px;">
            Averra PMS Dashboard
        </div>
        <div style="font-size: 0.85rem; color: #607a99; margin-bottom: 28px;">
            Enter your password to continue
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password", type="password", label_visibility="collapsed",
                            placeholder="Enter password...")
        if st.button("Login →", use_container_width=True, type="primary"):
            if pwd == "Averra3469":
                st.session_state["authenticated"] = True
                # Store auth token in URL — survives F5 refresh
                st.query_params["auth"] = "ok"
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    return False

if not check_password():
    st.stop()

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.7rem !important; font-weight: 700; }
    .block-container { padding-top: 1.5rem; }
    .section-title {
        font-size: 1.1rem; font-weight: 600; color: #e0e8f0;
        border-bottom: 2px solid #334966; padding-bottom: 6px; margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# ISIN → NSE TICKER MAP  (v2 — corrected)
#
# Symbols verified against NSE as of Mar 2026.
# To fix a "–" live price, find the correct symbol at:
#   https://www.nseindia.com  and update the entry below.
# Set to None for unlisted / SME stocks.
# ─────────────────────────────────────────────────────────────
ISIN_TO_NSE = {
    # ── CORRECTED in v2 ──────────────────────────────────────
    "INE151G01028": "SHAILY",        # was SHAILYENG  ✗
    "INE18JU01028": "EBGNG",          # confirmed NSE symbol
    "INE089C01029": "STLTECH",       # was STRTECH    ✗
    "INE064A01026": "TIMEX",          # BSE only — Yahoo uses TIMEX.BO
    "INE02YR01019": "EMIL",           # confirmed NSE symbol

    # ── Verified working ─────────────────────────────────────
    "INE00F201020": "PRUDENT",
    "INE00LO01017": "CRAFTSMAN",
    "INE040H01021": "SUZLON",
    "INE08U801020": "SAMHI",
    "INE090A01021": "ICICIBANK",
    "INE0KBH01020": "BLUEJET",
    "INE0UIZ01018": "BLACKBUCK",
    "INE118H01025": "BSE",
    "INE121J01017": "INDUSTOWER",
    "INE128S01021": "FIVESTAR",
    "INE180A01020": "MFSL",
    "INE191A01027": "ORCHPHARMA",
    "INE238A01034": "AXISBANK",
    "INE296A01032": "BAJFINANCE",
    "INE338H01029": "CONCORDBIO",
    "INE358U01012": "ZOTA",
    "INE397D01024": "BHARTIARTL",
    "INE417T01026": "POLICYBZR",
    "INE439E01022": "SKIPPER",
    "INE466L01038": "360ONE",
    "INE503A01015": "DCBBANK",
    "INE551W01018": "UJJIVANSFB",
    "INE646L01027": "INDIGO",
    "INE673O01025": "TBOTEK",
    "INE758T01015": "ETERNAL",
    "INE852O01025": "APTUS",
    "INE883F01010": "AADHARHFC",
    "INE947N01017": "AEQUS",
    "INE970X01018": "LEMONTREE",
    "INE995S01015": "NIVABUPA",
    "INF732E01037": "LIQUIDBEES",

    # ── Unlisted / SME — no live price ───────────────────────
    "INE013P01021": "ONESOURCE",  # NSE listed ✓
    "INE00FF01025": "ACUTAAS",    # NSE listed ✓
    "INE956O01016": "LENSKART",   # NSE listed Nov 2025 ✓
}

# Stocks listed on BSE only (not NSE) — use .BO suffix
BSE_ONLY = {
    "INE064A01026",   # Timex Group India — BSE only → TIMEX.BO
}

def get_ticker(isin: str):
    sym = ISIN_TO_NSE.get(isin)
    if not sym:
        return None
    suffix = ".BO" if isin in BSE_ONLY else ".NS"
    return f"{sym}{suffix}"

# ─────────────────────────────────────────────────────────────
# ALTERNATE TICKERS — tried if primary fails
# ─────────────────────────────────────────────────────────────
TICKER_ALTERNATES = {
    "GNGELECTRO.NS": ["GNG.NS", "GNGELECTRONICS.NS"],
    "TIMEXIND.NS":   ["TIMEX.NS", "TIMEXGRP.NS"],
    "EMARTINDIA.NS": ["EMARTIN.NS", "ELECTRONICSMART.NS"],
    "SHAILY.NS":     ["SHAILYENG.NS"],
    "STLTECH.NS":    ["STRTECH.NS", "STERLITETECH.NS"],
}



# ─────────────────────────────────────────────────────────────
# EXCEL PARSER
# ─────────────────────────────────────────────────────────────
def parse_nuvama_excel(uploaded_file) -> pd.DataFrame:
    # Accept either a file path (string) or a Streamlit UploadedFile object
    raw = pd.read_excel(uploaded_file, header=None)

    header_row_idx = None
    for i, row in raw.iterrows():
        vals = row.astype(str).str.upper().tolist()
        if "ISIN" in vals and any("INSTRUMENT" in v for v in vals):
            header_row_idx = i
            break

    if header_row_idx is None:
        st.error("Could not find the data header row (expected 'ISIN' + 'Instrument Name').")
        st.stop()

    df = pd.read_excel(uploaded_file, header=header_row_idx)  # works for path or file object
    df.columns = [str(c).strip() for c in df.columns]

    df = df[df["ISIN"].notna()]
    df = df[df["ISIN"].astype(str).str.match(r"^IN[A-Z0-9]{10}$")]

    for col in ["Logical Position", "Market Price", "Portfolio Value Client Currency"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Client Name"] = (
        df["Client Code"].astype(str)
        .str.split(r"\s+-\s+", n=1).str[-1].str.strip()
    )
    return df


def consolidate(df: pd.DataFrame) -> pd.DataFrame:
    grp = (
        df.groupby(["ISIN", "Instrument Name"], as_index=False)
        .agg(
            Total_Qty       = ("Logical Position", "sum"),
            Custodian_Price = ("Market Price", "first"),
            Num_Clients     = ("Client Name", "nunique"),
        )
    )
    grp["NSE_Ticker"] = grp["ISIN"].map(get_ticker)

    grp["Clean Name"] = (
        grp["Instrument Name"]
        .str.replace(r"\s+EQ\s*$",           "",    regex=True)
        .str.replace(r"\s+EQ\s+FV.*$",       "",    regex=True)
        .str.replace(r"\s+FV\s+.*$",         "",    regex=True)
        .str.replace(r"\s+FV[0-9].*$",       "",    regex=True)
        .str.replace(r"\s+UNLISTED$",        "",    regex=True)
        .str.replace(r"\bLIMITED\b",         "LTD", regex=True)
        .str.replace(r"EQ NEW FV RE\..*$",   "",    regex=True)
        .str.strip()
    )
    return grp.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# MARKET DATA
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=0, show_spinner=False)
def fetch_prices(tickers: list) -> dict:
    """
    Simple, reliable price fetch using only daily closes.
    Works consistently on both local and cloud environments.
    """
    valid = [t for t in tickers if t]
    if not valid:
        return {}
    results = {}

    # Single batch download — 1 year daily data
    # This gives us: today's close, prev close, and 52W range all in one call
    try:
        batch = yf.download(
            valid, period="1y", interval="1d",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True,
        )
    except Exception as e:
        st.warning(f"Price fetch error: {e}")
        return {}

    for t in valid:
        try:
            # Extract closes for this ticker
            if len(valid) == 1:
                closes = batch["Close"].dropna()
            else:
                if t not in batch.columns.get_level_values(0):
                    results[t] = None
                    continue
                closes = batch[t]["Close"].dropna()

            # Try alternates if empty
            if closes.empty:
                for alt in TICKER_ALTERNATES.get(t, []):
                    try:
                        alt_data = yf.download(alt, period="1y", interval="1d",
                                               auto_adjust=True, progress=False)
                        closes = alt_data["Close"].dropna()
                        if not closes.empty:
                            break
                    except Exception:
                        continue

            if closes.empty:
                results[t] = None
                continue

            # Latest close = today's price (or last trading day)
            live_price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else live_price
            day_c      = (live_price - prev_close) / prev_close * 100 if prev_close else 0.0

            # 52W from same data
            w52h = float(closes.max())
            w52l = float(closes.min())

            results[t] = {
                "price":       round(live_price, 2),
                "prev_close":  round(prev_close, 2),
                "day_chg_pct": round(day_c, 2),
                "w52h":        round(w52h, 2),
                "w52l":        round(w52l, 2),
            }
        except Exception:
            results[t] = None
    return results


@st.cache_data(ttl=300, show_spinner=False)
def fetch_benchmark():
    """Returns (1Y total return %, 1-day return %, live index price).
    Tries multiple BSE 500 / Sensex tickers as fallbacks."""
    candidates = ["^BSESN", "^BSE500", "BSE500.BO"]
    for symbol in candidates:
        try:
            bse = yf.download(symbol, period="1y", interval="1d",
                              auto_adjust=True, progress=False)
            c = bse["Close"].dropna()
            if len(c) < 2:
                continue
            live_price = float(c.iloc[-1])
            total = (live_price - float(c.iloc[0])) / float(c.iloc[0]) * 100
            day   = (live_price - float(c.iloc[-2])) / float(c.iloc[-2]) * 100
            return round(total, 2), round(day, 2), round(live_price, 2)
        except Exception:
            continue
    return None, None, None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV. Uses 1m interval for 1D, 5m for 5D, daily for rest."""
    interval_map = {
        "1d":  "1m",
        "5d":  "5m",
        "1mo": "1d",
        "3mo": "1d",
        "6mo": "1d",
        "1y":  "1d",
        "5y":  "1wk",
        "max": "1mo",
    }
    interval = interval_map.get(period, "1d")
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def fmt_inr(v):
    if v >= 1e7:  return f"₹{v/1e7:.2f} Cr"
    if v >= 1e5:  return f"₹{v/1e5:.2f} L"
    return f"₹{v:,.0f}"

def style_pnl(v):
    if pd.isna(v): return ""
    return f"color: {'#00c896' if v >= 0 else '#ff4d4d'}; font-weight: 600"

def style_alloc(v):
    if pd.isna(v): return ""
    alpha = min(v / 12, 1.0)  # normalise: 12% = full colour
    return f"background-color: rgba(46,100,180,{alpha:.2f}); color: #000; font-weight:600"


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 PMS Dashboard")
    st.caption("Averra Asset Managers LLP")
    st.divider()

    # ── Auto-load: works both locally AND on Streamlit Cloud ──
    import os, glob

    # Try local folder first (when running on your PC)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_files = sorted(
        glob.glob(os.path.join(script_dir, "*.xlsx")) +
        glob.glob(os.path.join(script_dir, "*.xls")),
        key=os.path.getmtime,
        reverse=True,
    )

    if excel_files:
        # Running locally — use file from folder
        auto_file = excel_files[0]
        st.success(f"✅ Auto-loaded: {os.path.basename(auto_file)}")
        if st.button("🔄 Reload File"):
            st.cache_data.clear()
            st.rerun()
        uploaded = auto_file
    else:
        # Running on Streamlit Cloud — look for Excel in repo root
        repo_excel = [f for f in os.listdir(".") if f.endswith((".xlsx", ".xls"))]
        if repo_excel:
            auto_file = sorted(repo_excel)[-1]
            st.success(f"✅ Auto-loaded: {auto_file}")
            if st.button("🔄 Reload File"):
                st.cache_data.clear()
                st.rerun()
            uploaded = auto_file
        else:
            # Last resort — manual upload
            st.warning("No Excel file found — please upload manually.")
            uploaded_new = st.file_uploader("Upload Nuvama Excel", type=["xlsx","xls"])
            if uploaded_new:
                st.session_state["uploaded_file"] = uploaded_new
            uploaded = st.session_state.get("uploaded_file", None)
    st.divider()
    # Chart period is selected via buttons on the chart itself
    st.divider()
    if st.button("🔄 Refresh prices now"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last loaded: {datetime.now().strftime('%d %b %Y %H:%M')}")


# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH
# ─────────────────────────────────────────────────────────────
# Clear price cache on every fresh page load
if "page_loaded" not in st.session_state:
    st.cache_data.clear()
    st.session_state["page_loaded"] = True

st.caption(f"🕐 Prices update on every page load  |  Last loaded: {datetime.now().strftime('%d %b %Y %H:%M')}  |  Press F5 to refresh")

# ─────────────────────────────────────────────────────────────
# LANDING
# ─────────────────────────────────────────────────────────────
if uploaded is None:
    st.title("📈 PMS Portfolio Dashboard")
    st.warning(
        "⚠️ No Excel file found. Place your **Nuvama Statement of Holding** Excel file "
        "in the same folder as `app.py`, then refresh the page."
    )
    st.stop()


# ─────────────────────────────────────────────────────────────
# PARSE + CONSOLIDATE
# ─────────────────────────────────────────────────────────────
with st.spinner("Parsing Excel…"):
    raw_df  = parse_nuvama_excel(uploaded)
    port_df = consolidate(raw_df)

n_clients = raw_df["Client Name"].nunique()
n_stocks  = len(port_df)


# ─────────────────────────────────────────────────────────────
# FETCH PRICES
# ─────────────────────────────────────────────────────────────
tickers = port_df["NSE_Ticker"].dropna().unique().tolist()
with st.spinner(f"Fetching live prices for {len(tickers)} stocks…"):
    price_data                   = fetch_prices(tickers)
    bse_ret, bse_day, bse_price  = fetch_benchmark()


# ─────────────────────────────────────────────────────────────
# ENRICH
# ─────────────────────────────────────────────────────────────
def gf(row, field):
    t = row["NSE_Ticker"]
    if t and price_data.get(t):
        return price_data[t].get(field)
    return None

port_df["Live Price"] = port_df.apply(lambda r: gf(r, "price"),       axis=1)
port_df["Prev Close"] = port_df.apply(lambda r: gf(r, "prev_close"),  axis=1)
port_df["Day Chg %"]  = port_df.apply(lambda r: gf(r, "day_chg_pct"), axis=1)
port_df["52W High"]   = port_df.apply(lambda r: gf(r, "w52h"),        axis=1)
port_df["52W Low"]    = port_df.apply(lambda r: gf(r, "w52l"),        axis=1)

port_df["Price Used"]   = port_df["Live Price"].combine_first(port_df["Custodian_Price"])
port_df["Market Value"] = port_df["Total_Qty"] * port_df["Price Used"]
port_df["Cust Value"]   = port_df["Total_Qty"] * port_df["Custodian_Price"]

total_market = port_df["Market Value"].sum()

# ── % Allocation ──────────────────────────────────────────────
port_df["% Alloc"] = (port_df["Market Value"] / total_market * 100).round(2)
port_df = port_df.sort_values("% Alloc", ascending=False).reset_index(drop=True)

# ── Price source label ────────────────────────────────────────
def price_src(row):
    if pd.notna(row["Live Price"]):    return "✅ Live"
    if row["NSE_Ticker"] is None:      return "🔒 Unlisted"
    return "⚠️ Check ticker"

port_df["Price Source"] = port_df.apply(price_src, axis=1)

# ── Totals ────────────────────────────────────────────────────
total_cust    = port_df["Cust Value"].sum()
total_pnl     = total_market - total_cust
total_pnl_pct = total_pnl / total_cust * 100 if total_cust else 0

valid_day    = port_df[port_df["Day Chg %"].notna() & (port_df["Market Value"] > 0)]
port_day_ret = 0.0
if not valid_day.empty:
    w = valid_day["Market Value"] / valid_day["Market Value"].sum()
    port_day_ret = (w * valid_day["Day Chg %"]).sum()

# 1-year alpha (overall P&L vs BSE500 1Y return)
alpha_1y  = (total_pnl_pct - bse_ret)  if bse_ret  is not None else None
# 1-day alpha  = portfolio day return minus BSE500 day return
alpha_1d  = (port_day_ret  - bse_day)  if bse_day  is not None else None

n_live   = port_df["Live Price"].notna().sum()
n_miss   = port_df["Live Price"].isna().sum()


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
st.title("📈 PMS Portfolio Dashboard")
st.caption(
    f"Averra Asset Managers LLP  ·  {n_clients} clients  ·  "
    f"{n_stocks} stocks  ·  ✅ {n_live} live  ·  ⚠️ {n_miss} custodian/unlisted"
)
st.divider()


# ─────────────────────────────────────────────────────────────
# KPI CARDS
# ─────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)

k1.metric("Total AUM",        fmt_inr(total_market))
k2.metric("Unrealised P&L",   fmt_inr(total_pnl), f"{total_pnl_pct:+.2f}%", delta_color="normal")
k3.metric("My 1-Day Return",  f"{port_day_ret:+.2f}%", delta_color="off")
k4.metric(
    "BSE 500",
    f"{bse_price:,.2f}" if bse_price else "N/A",
    f"{bse_day:+.2f}% today" if bse_day is not None else "",
    delta_color="normal",
)
k5.metric(
    "1-Day Alpha",
    f"{alpha_1d:+.2f}%" if alpha_1d is not None else "N/A",
    "Portfolio − BSE500 (today)",
    delta_color="off",
)
k6.metric(
    "Alpha vs BSE500 (1Y)",
    f"{alpha_1y:+.2f}%" if alpha_1y is not None else "N/A",
    f"BSE500 1Y: {bse_ret:.2f}%" if bse_ret else "",
    delta_color="normal",
)
st.divider()


# ─────────────────────────────────────────────────────────────
# HOLDINGS TABLE
# ─────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">📋 Consolidated Holdings — Portfolio Level</div>',
    unsafe_allow_html=True,
)

disp = port_df[[
    "Clean Name", "ISIN", "NSE_Ticker",
    "Total_Qty", "% Alloc",
    "Custodian_Price", "Live Price", "Day Chg %",
    "52W High", "52W Low",
    "Market Value",
    "Num_Clients",
]].copy()

disp.columns = [
    "Stock", "ISIN", "NSE Ticker",
    "Total Qty", "% Alloc",
    "Custodian Price", "Live Price", "Day Chg %",
    "52W High", "52W Low",
    "Market Value",
    "# Clients",
]

fp  = lambda x: f"₹{x:,.2f}" if pd.notna(x) else "–"
fc  = lambda x: f"{x:+.2f}%" if pd.notna(x) else "–"
fa  = lambda x: f"{x:.2f}%" if pd.notna(x) else "–"
fv  = lambda x: f"₹{x:,.0f}" if pd.notna(x) else "–"

styled = (
    disp.style
    .map(style_alloc, subset=["% Alloc"])
    .map(style_pnl,   subset=["Day Chg %"])
    .format({
        "Total Qty":        "{:,.0f}",
        "% Alloc":          fa,
        "Custodian Price":  fp,
        "Live Price":       fp,
        "Day Chg %":        fc,
        "52W High":         fp,
        "52W Low":          fp,
        "Market Value":     fv,
        "# Clients":        "{:.0f}",
    }, na_rep="–")
)

st.dataframe(styled, width="stretch", hide_index=True, height=520)

# ── Broken ticker helper ───────────────────────────────────────
broken = port_df[
    (port_df["NSE_Ticker"].notna()) & (port_df["Live Price"].isna())
]
if not broken.empty:
    with st.expander(f"⚠️ {len(broken)} ticker(s) not resolving — click to see & fix"):
        st.markdown(
            "These stocks have a ticker assigned but Yahoo Finance returned no price. "
            "Verify the symbol at [nseindia.com](https://www.nseindia.com) "
            "and update `ISIN_TO_NSE` at the top of the script."
        )
        st.dataframe(
            broken[["Clean Name","ISIN","NSE_Ticker","Custodian_Price"]]
            .rename(columns={
                "Clean Name":"Stock","NSE_Ticker":"Current Ticker (may be wrong)",
                "Custodian_Price":"Custodian Price",
            }),
            width="stretch", hide_index=True,
        )

st.divider()


# ─────────────────────────────────────────────────────────────
# CHARTS ROW 1 — Allocation pie + % Alloc bar
# ─────────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.markdown('<div class="section-title">🥧 Allocation by Market Value</div>',
                unsafe_allow_html=True)
    pie = port_df[port_df["Market Value"] > 0]
    fig_pie = px.pie(
        pie, names="Clean Name", values="Market Value", hole=0.42,
        color_discrete_sequence=px.colors.sequential.Blues_r,
        custom_data=["% Alloc"],
    )
    fig_pie.update_traces(
        textposition="inside", textinfo="percent+label", textfont_size=9,
        hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{customdata[0]:.2f}%<extra></extra>",
    )
    fig_pie.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#c8d8ea", showlegend=False,
        margin=dict(t=10,b=10,l=10,r=10), height=400,
    )
    st.plotly_chart(fig_pie, width="stretch")

with col_r:
    st.markdown('<div class="section-title">📊 % Allocation — All Holdings</div>',
                unsafe_allow_html=True)
    alloc_sorted = port_df.sort_values("% Alloc")
    fig_bar = go.Figure(go.Bar(
        x=alloc_sorted["% Alloc"],
        y=alloc_sorted["Clean Name"],
        orientation="h",
        marker=dict(color=alloc_sorted["% Alloc"], colorscale="Blues", showscale=False),
        text=[f"{v:.2f}%" for v in alloc_sorted["% Alloc"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.2f}% of AUM<extra></extra>",
    ))
    fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#c8d8ea",
        xaxis=dict(showgrid=True, gridcolor="#1e3a5f", title="% of AUM"),
        yaxis=dict(showgrid=False),
        margin=dict(t=10,b=10,l=10,r=60),
        height=400,
    )
    st.plotly_chart(fig_bar, width="stretch")

st.divider()


# ─────────────────────────────────────────────────────────────
# CHARTS ROW 2 — Day change
# ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Today\'s Move (Day Chg %)</div>',
            unsafe_allow_html=True)

day_df = port_df[port_df["Day Chg %"].notna()].sort_values("Day Chg %")
colors = ["#ff4d4d" if v < 0 else "#00c896" for v in day_df["Day Chg %"]]

fig_day = go.Figure(go.Bar(
    x=day_df["Day Chg %"],
    y=day_df["Clean Name"],
    orientation="h",
    marker_color=colors,
    text=[f"{v:+.2f}%" for v in day_df["Day Chg %"]],
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>Day: %{x:+.2f}%<extra></extra>",
))
fig_day.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font_color="#c8d8ea",
    xaxis=dict(showgrid=True, gridcolor="#1e3a5f", title="Day Change %",
               zeroline=True, zerolinecolor="#556677"),
    yaxis=dict(showgrid=False),
    margin=dict(t=10,b=10,l=10,r=70),
    height=max(300, len(day_df)*26),
)
st.plotly_chart(fig_day, width="stretch")
st.divider()


# ─────────────────────────────────────────────────────────────
# CLIENT BREAKDOWN
# ─────────────────────────────────────────────────────────────
with st.expander("👥 Client-wise Breakdown"):
    cg = (
        raw_df.groupby("Client Name", as_index=False)
        .agg(Stocks=("ISIN","nunique"), Portfolio_Value=("Portfolio Value Client Currency","sum"))
        .sort_values("Portfolio_Value", ascending=False)
    )
    cg["% of AUM"]       = (cg["Portfolio_Value"] / cg["Portfolio_Value"].sum() * 100).round(2)
    cg["Portfolio Value"] = cg["Portfolio_Value"].map(lambda x: f"₹{x:,.0f}")
    cg["% of AUM"]       = cg["% of AUM"].map(lambda x: f"{x:.2f}%")
    st.dataframe(cg[["Client Name","Stocks","Portfolio Value","% of AUM"]],
                 width="stretch", hide_index=True)


# ─────────────────────────────────────────────────────────────
# STOCK DEEP DIVE
# ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🔍 Stock Chart</div>', unsafe_allow_html=True)

tradeable = port_df[port_df["NSE_Ticker"].notna()].copy()

if tradeable.empty:
    st.info("No NSE-listed stocks for chart.")
else:
    # Stock selector + period buttons on same row
    col_sel, col_periods = st.columns([2, 3])

    with col_sel:
        selected = st.selectbox("Select stock", tradeable["Clean Name"].tolist(), label_visibility="collapsed")

    with col_periods:
        periods     = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"]
        period_labels = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y", "Max"]
        if "chart_period_sel" not in st.session_state:
            st.session_state.chart_period_sel = "1y"
        cols = st.columns(len(periods))
        for i, (p, lbl) in enumerate(zip(periods, period_labels)):
            if cols[i].button(
                lbl,
                key=f"period_{p}",
                type="primary" if st.session_state.chart_period_sel == p else "secondary",
            ):
                st.session_state.chart_period_sel = p
                st.rerun()
        active_period = st.session_state.chart_period_sel

    sel     = tradeable[tradeable["Clean Name"] == selected].iloc[0]
    st_tick = sel["NSE_Ticker"]
    pdata   = price_data.get(st_tick) or {}

    # Metrics row
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Live Price",     f"₹{pdata['price']:,.2f}"        if pdata.get("price")           else "N/A")
    m2.metric("Day Change",     f"{pdata['day_chg_pct']:+.2f}%"  if pdata.get("day_chg_pct") is not None else "N/A", delta_color="normal")
    m3.metric("52W High",       f"₹{pdata['w52h']:,.2f}"         if pdata.get("w52h")            else "N/A")
    m4.metric("52W Low",        f"₹{pdata['w52l']:,.2f}"         if pdata.get("w52l")            else "N/A")
    m5.metric("Total Qty",      f"{int(sel['Total_Qty']):,}")
    m6.metric("% of Portfolio", f"{sel['% Alloc']:.2f}%")

    hist = fetch_history(st_tick, period=active_period)

    if not hist.empty:
        closes = hist["Close"].squeeze()
        dates  = hist.index

        # Colour: green if last price >= first, red if down
        start_p = float(closes.iloc[0])
        end_p   = float(closes.iloc[-1])
        line_color = "#00c896" if end_p >= start_p else "#ff4d4d"
        fill_color = "rgba(0,200,150,0.08)" if end_p >= start_p else "rgba(255,77,77,0.08)"

        fig = go.Figure()

        # Main price line
        fig.add_trace(go.Scatter(
            x=dates,
            y=closes,
            mode="lines",
            line=dict(color=line_color, width=2),
            fill="tozeroy",
            fillcolor=fill_color,
            name=selected,
            hovertemplate="₹%{y:,.2f}<br>%{x}<extra></extra>",
        ))

        # Custodian price reference line
        cp = float(sel["Custodian_Price"])
        if cp > 0:
            fig.add_hline(
                y=cp, line_dash="dash", line_color="#7fa8f5", line_width=1,
                annotation_text=f"Avg Cost ₹{cp:,.0f}",
                annotation_font_color="#7fa8f5",
                annotation_position="right",
            )

        fig.update_layout(
            title=f"{selected}  ·  {int(sel['Total_Qty']):,} shares  ·  {sel['% Alloc']:.2f}% of AUM",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#c8d8ea",
            xaxis=dict(
                showgrid=False,
                showline=False,
                zeroline=False,
                rangeslider_visible=False,
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#1e3a5f",
                title="Price (₹)",
                zeroline=False,
            ),
            hovermode="x unified",
            height=420,
            margin=dict(t=50, b=10, l=10, r=80),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning(f"No price history for **{st_tick}**. Check / update the ticker in `ISIN_TO_NSE`.")

# ─────────────────────────────────────────────────────────────
# STOCK NEWS  (Marketaux API)
# ─────────────────────────────────────────────────────────────
MARKETAUX_API_KEY = "xO9s6K428gqzV36DTHVXxNXOQjZJHFOJzq1apu8g"

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(ticker: str, company_name: str) -> list:
    """Fetch latest news for a stock from Marketaux API."""
    import requests

    # Strip .NS / .BO for Marketaux — it uses NSE symbols without suffix
    clean_ticker = ticker.replace(".NS", "").replace(".BO", "")

    # Try by ticker symbol first, then by company name
    results = []
    for search_term, use_ticker in [(clean_ticker, True), (company_name, False)]:
        try:
            params = {
                "api_token": MARKETAUX_API_KEY,
                "limit":     10,
                "language":  "en",
                "countries": "in",
            }
            if use_ticker:
                params["symbols"] = search_term
            else:
                params["search"] = search_term[:40]  # trim long names

            resp = requests.get(
                "https://api.marketaux.com/v1/news/all",
                params=params,
                timeout=10,
            )
            data = resp.json()
            articles = data.get("data", [])
            if articles:
                results = articles
                break
        except Exception:
            continue
    return results


def sentiment_badge(score):
    """Return coloured sentiment label."""
    if score is None:
        return ""
    if score > 0.1:
        return f'<span style="background:#00c896;color:#000;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600">▲ Positive</span>'
    elif score < -0.1:
        return f'<span style="background:#ff4d4d;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600">▼ Negative</span>'
    else:
        return f'<span style="background:#888;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600">● Neutral</span>'


# Only show news if a stock is selected
if "selected" in dir() and selected:
    st.divider()
    st.markdown(
        f'<div class="section-title">📰 Latest News — {selected}</div>',
        unsafe_allow_html=True,
    )

    with st.spinner("Fetching latest news..."):
        # Use the clean company name for better search
        company_search = sel["Clean Name"] if "sel" in dir() else selected
        articles = fetch_news(st_tick if "st_tick" in dir() else "", company_search)

    if not articles:
        st.info("No recent news found for this stock. Try selecting a different stock.")
    else:
        for article in articles:
            title       = article.get("title", "No title")
            url         = article.get("url", "#")
            source      = article.get("source", "Unknown")
            published   = article.get("published_at", "")
            description = article.get("description", "")
            entities    = article.get("entities", [])

            # Get sentiment from entities matching our stock
            sentiment_score = None
            for entity in entities:
                if entity.get("type") == "equity":
                    sentiment_score = entity.get("sentiment_score")
                    break

            # Format published date
            try:
                from datetime import datetime as dt
                pub_dt = dt.strptime(published[:19], "%Y-%m-%dT%H:%M:%S")
                pub_str = pub_dt.strftime("%d %b %Y %H:%M")
            except Exception:
                pub_str = published[:10]

            # Render news card
            st.markdown(f"""
            <div style="
                border: 1px solid #2e3a4a;
                border-radius: 10px;
                padding: 14px 18px;
                margin-bottom: 10px;
                background: #0e1a2b;
            ">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
                    <a href="{url}" target="_blank" style="
                        color: #e0e8f0;
                        font-size: 0.95rem;
                        font-weight: 600;
                        text-decoration: none;
                        flex: 1;
                        line-height: 1.4;
                    ">{title}</a>
                    <div style="white-space:nowrap">{sentiment_badge(sentiment_score)}</div>
                </div>
                <div style="margin-top: 8px; font-size: 0.78rem; color: #607a99;">
                    {source}  ·  {pub_str}
                </div>
                {"<div style='margin-top:6px; font-size:0.82rem; color:#8aa8cc; line-height:1.4'>" + description[:180] + "...</div>" if description else ""}
            </div>
            """, unsafe_allow_html=True)


# Prices refresh every 10 min via cache TTL, or when user manually refreshes the page.
