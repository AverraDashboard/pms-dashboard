"""
Averra Portfolio Dashboard
============================
Works with the Nuvama "Statement of Holding" Excel export.

Install:
    pip install streamlit yfinance pandas openpyxl plotly bse requests

Run:
    streamlit run app.py

Requires news_fetch.py and watchlist.json in the same folder for the
News & BSE Filings feed at the bottom of the dashboard.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import time
from datetime import datetime

# news_fetch.py must sit alongside this file. Imported defensively so a
# missing/broken news module degrades the news section only — it should
# never take down the rest of the dashboard (prices, holdings, etc.).
try:
    import news_fetch
    NEWS_MODULE_AVAILABLE = True
except Exception as _news_import_err:
    NEWS_MODULE_AVAILABLE = False
    _NEWS_IMPORT_ERROR = str(_news_import_err)

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Averra Portfolio Dashboard",
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

    "INE867C01010": "ASMTEC",         # ASM Technologies — BSE only → ASMTEC.BO
    "INE221B01012": "DYNAMATECH",      # Dynamatic Technologies — NSE listed
    "INE552U01010": "KPL",             # Kwality Pharmaceuticals — NSE listed
    "INE922K01024": "INDIASHLTR",      # India Shelter Finance Corporation — NSE listed
    "INE349A01021": "NRBBEARING",      # NRB Bearings — NSE listed
    "INE15B701018": "PINELABS",         # Pine Labs — NSE listed (IPO Nov 2025)
    # ── Unlisted / SME — no live price ───────────────────────
    "INE013P01021": "ONESOURCE",  # NSE listed ✓
    "INE00FF01025": "ACUTAAS",    # NSE listed ✓
    "INE956O01016": "LENSKART",   # NSE listed Nov 2025 ✓
}

# Stocks listed on BSE only (not NSE) — use .BO suffix
BSE_ONLY = {
    "INE064A01026",   # Timex Group India — BSE only → TIMEX.BO
    "INE867C01010",   # ASM Technologies — BSE only → ASMTECH.BO
}

CUSTOM_TICKER_FILE = "custom_tickers.csv"

def load_custom_tickers() -> dict:
    import os
    if not os.path.exists(CUSTOM_TICKER_FILE):
        return {}
    try:
        df = pd.read_csv(CUSTOM_TICKER_FILE)
        result = {}
        for _, row in df.iterrows():
            isin   = str(row.get("ISIN","")).strip()
            ticker = str(row.get("Ticker","")).strip()
            if isin and ticker and isin != "nan" and ticker != "nan":
                result[isin] = ticker
        return result
    except Exception:
        return {}

def save_custom_ticker(isin: str, ticker: str, exchange: str) -> str:
    ticker = ticker.upper().strip()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + (".BO" if exchange == "BSE" else ".NS")
    existing = load_custom_tickers()
    existing[isin.strip()] = ticker
    rows = [{"ISIN": k, "Ticker": v} for k, v in existing.items()]
    pd.DataFrame(rows).to_csv(CUSTOM_TICKER_FILE, index=False)
    return ticker

def delete_custom_ticker(isin: str):
    existing = load_custom_tickers()
    existing.pop(isin.strip(), None)
    rows = [{"ISIN": k, "Ticker": v} for k, v in existing.items()]
    pd.DataFrame(rows).to_csv(CUSTOM_TICKER_FILE, index=False)

def get_ticker(isin: str):
    sym = ISIN_TO_NSE.get(isin)
    if sym:
        suffix = ".BO" if isin in BSE_ONLY else ".NS"
        return f"{sym}{suffix}"
    custom = load_custom_tickers()
    if isin in custom:
        return custom[isin]
    return None

# ─────────────────────────────────────────────────────────────
# ALTERNATE TICKERS — tried if primary fails
# ─────────────────────────────────────────────────────────────
TICKER_ALTERNATES = {
    "GNGELECTRO.NS": ["GNG.NS", "GNGELECTRONICS.NS"],
    "TIMEXIND.NS":   ["TIMEX.NS", "TIMEXGRP.NS"],
    "EMARTINDIA.NS": ["EMARTIN.NS", "ELECTRONICSMART.NS"],
    "SHAILY.NS":     ["SHAILYENG.NS"],
    "STLTECH.NS":    ["STRTECH.NS", "STERLITETECH.NS"],
    "KPL.NS":        ["KPL.BO"],   # Kwality Pharma — try BSE if NSE stale
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


def parse_master_portfolio(filepath) -> pd.DataFrame:
    """
    Parse Master_Model_Portfolio.xlsx.
    Returns DataFrame with columns: ISIN, FY27_EPS, FY28_EPS, Target_FY27, Target_FY28
    """
    if filepath is None:
        return pd.DataFrame(columns=["ISIN","FY27_EPS","FY28_EPS","Target_FY27","Target_FY28"])
    try:
        df = pd.read_excel(filepath, header=0)
        df.columns = [str(c).strip() for c in df.columns]
        # Rename columns to standard names
        col_map = {}
        for c in df.columns:
            cu = c.upper()
            if "ISIN" in cu:                              col_map[c] = "ISIN"
            elif "2027 TARGET" in cu or ("TARGET" in cu and "27" in cu): col_map[c] = "Target_FY27"
            elif "2028 TARGET" in cu or ("TARGET" in cu and "28" in cu): col_map[c] = "Target_FY28"
            elif "EPS" in cu and "27" in cu:              col_map[c] = "FY27_EPS"
            elif "EPS" in cu and "28" in cu:              col_map[c] = "FY28_EPS"
        df = df.rename(columns=col_map)
        for col in ["ISIN","FY27_EPS","FY28_EPS","Target_FY27","Target_FY28"]:
            if col not in df.columns:
                df[col] = None
        for col in ["FY27_EPS","FY28_EPS","Target_FY27","Target_FY28"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["ISIN"] = df["ISIN"].astype(str).str.strip()
        return df[["ISIN","FY27_EPS","FY28_EPS","Target_FY27","Target_FY28"]].dropna(subset=["ISIN"])
    except Exception as e:
        st.warning(f"Could not load Master Portfolio: {e}")
        return pd.DataFrame(columns=["ISIN","FY27_EPS","FY28_EPS","Target_FY27","Target_FY28"])


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
    """
    Returns (1Y total return %, 1-day return %, live index price).
    Fetches BSE 500 live price directly from BSE India website,
    falls back to Yahoo Finance if that fails.
    """
    import requests

    # Method 1: Scrape BSE India directly — same source as bseindia.com
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer":    "https://www.bseindia.com/",
        }
        url = "https://api.bseindia.com/BseIndiaAPI/api/GetIndexData/w?index=BSE%20500"
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        live_price = float(data.get("CurrValue", 0))
        prev_close = float(data.get("PrevClose", live_price))
        day        = float(data.get("PerChange", 0))
        if live_price > 0:
            # Get 1Y return from Yahoo as fallback for this one metric
            try:
                hist = yf.download("BSE-500.BO", period="1y", interval="1d",
                                   auto_adjust=True, progress=False)
                c1y  = hist["Close"].dropna()
                total = (live_price - float(c1y.iloc[0])) / float(c1y.iloc[0]) * 100 if len(c1y) > 1 else 0
            except Exception:
                total = 0
            return round(total, 2), round(day, 2), round(live_price, 2)
    except Exception:
        pass

    # Method 2: Yahoo Finance fallback
    for symbol in ["BSE-500.BO", "^BSESN", "^BSE500"]:
        try:
            bse_5d = yf.download(symbol, period="5d", interval="1d",
                                 auto_adjust=True, progress=False)
            c_5d = bse_5d["Close"].dropna()
            if len(c_5d) < 2:
                continue
            live_price = float(c_5d.iloc[-1])
            prev_close = float(c_5d.iloc[-2])
            day   = (live_price - prev_close) / prev_close * 100
            bse_1y = yf.download(symbol, period="1y", interval="1d",
                                 auto_adjust=True, progress=False)
            c_1y  = bse_1y["Close"].dropna()
            total = (live_price - float(c_1y.iloc[0])) / float(c_1y.iloc[0]) * 100 if len(c_1y) > 1 else 0
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

    def _is_master(fname):
        n = os.path.basename(str(fname)).upper()
        return "MASTER" in n or "MODEL" in n

    def _find_files():
        """Find all Excel files — checks local folder first, then cloud (repo root)."""
        import re
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Local: sort by modification time (most recent first)
        local = sorted(
            glob.glob(os.path.join(script_dir, "*.xlsx")) +
            glob.glob(os.path.join(script_dir, "*.xls")),
            key=os.path.getmtime, reverse=True,
        )
        if local:
            return local, "local"
        # Cloud: sort by date in filename (DD-MM-YYYY pattern) — most recent first
        # Falls back to reverse alphabetical if no date found
        def _file_sort_key(fname):
            base = os.path.basename(fname).upper()
            # Extract date from filename like "AS ON 05-06-2026"
            m = re.search(r"(\d{2})-(\d{2})-(\d{4})", base)
            if m:
                d, mo, y = m.group(1), m.group(2), m.group(3)
                return f"{y}{mo}{d}"  # YYYYMMDD → sorts correctly
            return base  # fallback
        cloud = sorted(
            [f for f in os.listdir(".") if f.endswith((".xlsx", ".xls"))],
            key=_file_sort_key, reverse=True,  # most recent date first
        )
        return cloud, "cloud"

    all_files, file_source = _find_files()

    nuvama_files = [f for f in all_files if not _is_master(f)]
    master_files = [f for f in all_files if _is_master(f)]

    uploaded    = nuvama_files[0] if nuvama_files else None
    master_file = master_files[0] if master_files else None

    # Show which files are loaded with their actual filenames
    st.caption(f"📂 Source: {'Local folder' if file_source == 'local' else 'GitHub repo'}")
    if all_files:
        st.caption("Files found: " + " | ".join([os.path.basename(str(f)) for f in all_files]))

    if uploaded:
        st.success(f"✅ Holdings: {os.path.basename(str(uploaded))}")
    if master_file:
        st.success(f"✅ Master Portfolio: {os.path.basename(str(master_file))}")
    else:
        st.warning("⚠️ Master_Model_Portfolio.xlsx not found in repo — upload it to GitHub.")

    if st.button("🔄 Reload Files"):
        # Clear ALL cache including file cache
        st.cache_data.clear()
        st.cache_resource.clear()
        # Reset session so files are re-read from disk
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    if not uploaded:
        st.warning("No holdings Excel found — please upload to GitHub.")

    st.divider()
    st.markdown("### ➕ Manage Tickers")
    st.caption("New stock showing no price? Add it here.")

    with st.form("add_ticker_form", clear_on_submit=True):
        new_isin   = st.text_input("ISIN", placeholder="e.g. INE15B701018")
        new_ticker = st.text_input("NSE/BSE Symbol", placeholder="e.g. PINELABS")
        new_exch   = st.radio("Exchange", ["NSE", "BSE"], horizontal=True)
        submitted  = st.form_submit_button("✅ Save Ticker")
        if submitted:
            if new_isin.strip() and new_ticker.strip():
                saved = save_custom_ticker(new_isin, new_ticker, new_exch)
                st.success(f"Saved: {new_isin.strip()} → {saved}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Please fill in both ISIN and Symbol.")

    custom_map = load_custom_tickers()
    if custom_map:
        st.caption("**Saved custom tickers:**")
        for isin, ticker in list(custom_map.items()):
            c1, c2 = st.columns([3, 1])
            c1.caption(f"`{isin}` → `{ticker}`")
            if c2.button("🗑", key=f"del_{isin}"):
                delete_custom_ticker(isin)
                st.cache_data.clear()
                st.rerun()

    st.divider()
    # Chart period is selected via buttons on the chart itself
    st.divider()
    if st.button("🔄 Refresh prices now"):
        st.cache_data.clear()
        st.session_state["_do_news_topup"] = True  # also check for new news/filings
        st.rerun()
    st.caption(f"Last loaded: {datetime.now().strftime('%d %b %Y %H:%M')}")


# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH
# ─────────────────────────────────────────────────────────────
# Cache clears automatically via TTL — no session state needed

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
    raw_df   = parse_nuvama_excel(uploaded)
    port_df  = consolidate(raw_df)
    master_df = parse_master_portfolio(master_file)

n_clients = raw_df["Client Name"].nunique()
n_stocks  = len(port_df)


# ─────────────────────────────────────────────────────────────
# AUTO-DETECT MISSING TICKERS
# ─────────────────────────────────────────────────────────────
def _guess_ticker(name: str):
    """Guess Yahoo Finance ticker from company name — tries NSE then BSE."""
    clean = (name.upper()
             .replace(" LIMITED","").replace(" LTD","")
             .replace(" PRIVATE","").replace(" PVT","")
             .replace(" CORPORATION","").replace(" CORP","")
             .replace(" FINANCE","").replace(" FINANCIAL","")
             .replace(" TECHNOLOGIES","").replace(" TECH","")
             .replace(" INDUSTRIES","").replace(" IND","")
             .replace(" PHARMACEUTICALS","").replace(" PHARMA","")
             .replace(" SOLUTIONS","").replace(" SERVICES","")
             .replace(" INDIA","").replace(" HOLDINGS","")
             .replace("-","").replace(" ","").strip())
    for suffix in [".NS", ".BO"]:
        try:
            t = f"{clean}{suffix}"
            hist = yf.download(t, period="5d", interval="1d",
                               auto_adjust=True, progress=False)
            if not hist.empty and len(hist["Close"].dropna()) > 0:
                return t
        except Exception:
            continue
    return None

missing = port_df["NSE_Ticker"].isna()
if missing.any():
    with st.spinner("Auto-detecting tickers for new stocks…"):
        for idx, row in port_df[missing].iterrows():
            detected = _guess_ticker(row["Instrument Name"])
            if detected:
                port_df.at[idx, "NSE_Ticker"] = detected

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

# ── Merge Master Portfolio data ───────────────────────────────────────────
if not master_df.empty:
    port_df = port_df.merge(master_df, on="ISIN", how="left")
else:
    port_df["FY27_EPS"]     = None
    port_df["FY28_EPS"]     = None
    port_df["Target_FY27"]  = None
    port_df["Target_FY28"]  = None

# ── Calculated columns (live price driven) ───────────────────────────────
lp = port_df["Live Price"]

port_df["FY27_PE"] = (lp / port_df["FY27_EPS"]).where(
    port_df["FY27_EPS"].notna() & (port_df["FY27_EPS"] > 0), None)

port_df["FY28_PE"] = (lp / port_df["FY28_EPS"]).where(
    port_df["FY28_EPS"].notna() & (port_df["FY28_EPS"] > 0), None)

port_df["Upside_FY27"] = ((port_df["Target_FY27"] / lp) - 1) * 100
port_df["Upside_FY28"] = ((port_df["Target_FY28"] / lp) - 1) * 100

# IRR: CAGR from today to 31 March 2028
from datetime import date
today    = date.today()
exit_date= date(2028, 3, 31)
years    = (exit_date - today).days / 365.25
if years > 0:
    port_df["IRR_FY28"] = ((port_df["Target_FY28"] / lp) ** (1 / years) - 1) * 100
else:
    port_df["IRR_FY28"] = None

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
hdr_l, hdr_r = st.columns([5, 1])
with hdr_l:
    st.title("📈 Averra Portfolio Dashboard")
    st.caption(
        f"Averra Asset Managers LLP  ·  {n_clients} clients  ·  "
        f"{n_stocks} stocks  ·  ✅ {n_live} live  ·  ⚠️ {n_miss} custodian/unlisted"
    )
with hdr_r:
    import os as _os
    _logo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "averra_logo.png")
    if _os.path.exists(_logo_path):
        st.image(_logo_path, width=130)
st.divider()


# ─────────────────────────────────────────────────────────────
# KPI CARDS
# ─────────────────────────────────────────────────────────────
k1, k2 = st.columns(2)

k1.metric("Total AUM",        fmt_inr(total_market))
k2.metric("My 1-Day Return",  f"{port_day_ret:+.2f}%", delta_color="off")
st.divider()


# ─────────────────────────────────────────────────────────────
# HOLDINGS TABLE
# ─────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">📋 Consolidated Holdings — Portfolio Level</div>',
    unsafe_allow_html=True,
)

disp = port_df[[
    "Clean Name", "% Alloc",
    "Live Price", "Day Chg %",
    "IRR_FY28",
    "FY27_PE",  "FY28_PE",
    "ISIN", "Total_Qty",
    "Market Value",
    "FY27_EPS", "FY28_EPS",
    "Target_FY27", "Upside_FY27",
    "Target_FY28", "Upside_FY28",
]].copy()

disp.columns = [
    "Stock", "% Alloc",
    "Live Price", "Day Chg %",
    "IRR to Mar'28",
    "FY27 PE",  "FY28 PE",
    "ISIN", "Total Qty",
    "Market Value",
    "FY27 EPS", "FY28 EPS",
    "Mar'27 Target", "Mar'27 Upside %",
    "Mar'28 Target", "Mar'28 Upside %",
]

fp  = lambda x: f"₹{x:,.2f}"  if pd.notna(x) else "–"
fc  = lambda x: f"{x:+.2f}%"   if pd.notna(x) else "–"
fa  = lambda x: f"{x:.2f}%"    if pd.notna(x) else "–"
fv  = lambda x: f"₹{x:,.0f}"  if pd.notna(x) else "–"
fpe = lambda x: f"{x:.1f}x"   if pd.notna(x) else "–"
fup = lambda x: f"{x:+.1f}%"  if pd.notna(x) else "–"

def style_upside(v):
    if pd.isna(v): return ""
    return f"color: {'#00c896' if v >= 0 else '#ff4d4d'}; font-weight:600"

styled = (
    disp.style
    .map(style_alloc,  subset=["% Alloc"])
    .map(style_pnl,    subset=["Day Chg %"])
    .map(style_upside, subset=["Mar'27 Upside %", "Mar'28 Upside %", "IRR to Mar'28"])
    .format({
        "Total Qty":        "{:,.0f}",
        "% Alloc":          fa,
        "Live Price":       fp,
        "Day Chg %":        fc,
        "Market Value":     fv,
        "FY27 EPS":         lambda x: f"{x:.2f}" if pd.notna(x) else "–",
        "FY28 EPS":         lambda x: f"{x:.2f}" if pd.notna(x) else "–",
        "FY27 PE":          fpe,
        "FY28 PE":          fpe,
        "Mar'27 Target":    fp,
        "Mar'27 Upside %":  fup,
        "Mar'28 Target":    fp,
        "Mar'28 Upside %":  fup,
        "IRR to Mar'28":    fup,
    }, na_rep="–")
)

holdings_event = st.dataframe(
    styled, width="stretch", hide_index=True, height=520,
    on_select="rerun", selection_mode="single-row", key="holdings_table",
)

# Capture which stock (if any) was clicked — drives the news feed below.
# disp.index lines up with the styled/displayed dataframe's row order.
_clicked_rows = holdings_event.get("selection", {}).get("rows", []) if holdings_event else []
clicked_stock_name = disp.iloc[_clicked_rows[0]]["Stock"] if _clicked_rows else None
clicked_stock_isin = disp.iloc[_clicked_rows[0]]["ISIN"] if _clicked_rows else None

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
            broken[["Clean Name","ISIN","NSE_Ticker"]]
            .rename(columns={"Clean Name":"Stock","NSE_Ticker":"Ticker (check symbol)"}),
            width="stretch", hide_index=True,
        )

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
    m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
    m1.metric("Live Price",     f"₹{pdata['price']:,.2f}"       if pdata.get("price")                    else "N/A")
    m2.metric("Day Change",     f"{pdata['day_chg_pct']:+.2f}%" if pdata.get("day_chg_pct") is not None  else "N/A", delta_color="normal")
    m3.metric("% of Portfolio", f"{sel['% Alloc']:.2f}%")
    m4.metric("FY27 PE",        f"{sel['FY27_PE']:.1f}x"        if pd.notna(sel.get('FY27_PE'))          else "N/A")
    m5.metric("FY28 PE",        f"{sel['FY28_PE']:.1f}x"        if pd.notna(sel.get('FY28_PE'))          else "N/A")
    m6.metric("Mar'27 Upside",  f"{sel['Upside_FY27']:+.1f}%"   if pd.notna(sel.get('Upside_FY27'))      else "N/A")
    m7.metric("Mar'28 Upside",  f"{sel['Upside_FY28']:+.1f}%"   if pd.notna(sel.get('Upside_FY28'))      else "N/A")
    m8.metric("IRR to Mar'28",  f"{sel['IRR_FY28']:+.1f}%"      if pd.notna(sel.get('IRR_FY28'))         else "N/A")

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
# NEWS & BSE FILINGS FEED
# ─────────────────────────────────────────────────────────────
# Behaviour (as agreed):
#   - Plain browser refresh (F5) -> brand new Streamlit session -> full
#     rebuild of the feed from scratch.
#   - "Refresh prices now" button -> same script rerun, but session_state
#     SURVIVES -> incremental top-up: fetch again, but only PREPEND items
#     that are genuinely new (not already showing), rather than rebuilding
#     the whole list. This keeps the button fast/cheap-feeling even though
#     a real fetch happens underneath.
#   - Clicking a stock row in the holdings table -> filters the feed to
#     just that company. News: 10 most recent (uncapped by time, "load
#     more" reaches further back). BSE: strictly last 72 hours, no
#     backfill.
#   - Default (nothing clicked): same rules, applied across all holdings,
#     merged into one recency-sorted feed.

st.divider()
st.markdown('<div class="section-title">📰 News & BSE Filings</div>', unsafe_allow_html=True)

if not NEWS_MODULE_AVAILABLE:
    st.error(
        f"News module could not be loaded ({_NEWS_IMPORT_ERROR}). "
        f"Make sure `news_fetch.py` and `watchlist.json` are uploaded to the same "
        f"GitHub folder as `app.py`, and that `bse` + `requests` are installed."
    )
else:
    # ── Session-state-backed fetch: distinguishes "fresh session" (F5)
    # from "button click within the same session" (price refresh) ──
    if "news_feed_all" not in st.session_state:
        # Brand new session -> this is a true page (re)load -> full fetch
        with st.spinner("Fetching news & BSE filings across your portfolio…"):
            st.session_state.news_feed_all = news_fetch.get_portfolio_wide_feed(
                news_count=10, bse_hours=72,
            )
        st.session_state.news_feed_fetched_at = datetime.now()

    if "news_feed_per_stock" not in st.session_state:
        st.session_state.news_feed_per_stock = {}  # isin -> list, cached per stock clicked this session

    # ── Incremental top-up, triggered by the existing price-refresh flow ──
    # The sidebar's "Refresh prices now" button calls st.cache_data.clear()
    # + st.rerun(). We piggyback on a session_state flag so THIS section
    # can tell "the user just asked for a refresh" apart from "this is a
    # brand-new page load" (session_state wouldn't exist at all in that
    # case, handled above).
    if st.session_state.get("_do_news_topup"):
        with st.spinner("Checking for newer items…"):
            fresh = news_fetch.get_portfolio_wide_feed(news_count=10, bse_hours=72)
        existing_urls = {item.get("url") for item in st.session_state.news_feed_all}
        new_items = [item for item in fresh if item.get("url") not in existing_urls]
        if new_items:
            st.session_state.news_feed_all = new_items + st.session_state.news_feed_all
            st.toast(f"📰 {len(new_items)} new item(s) added to the feed")
        st.session_state["_do_news_topup"] = False

    # ── Manual "check for updates now" control for the news feed itself ──
    topup_col, ts_col = st.columns([1, 4])
    with topup_col:
        if st.button("🔄 Check for news updates"):
            st.session_state["_do_news_topup"] = True
            st.rerun()
    with ts_col:
        fetched_at = st.session_state.get("news_feed_fetched_at")
        if fetched_at:
            st.caption(f"Last updated: {fetched_at.strftime('%d %b %Y, %H:%M')}")

    # ── Render: per-stock filtered view if a row was clicked, else portfolio-wide ──
    if clicked_stock_isin:
        clear_col, label_col = st.columns([1, 4])
        with clear_col:
            if st.button("✕ Clear filter"):
                st.session_state["holdings_table"] = {"selection": {"rows": []}}
                st.rerun()
        with label_col:
            st.markdown(f"**Showing: {clicked_stock_name}**")

        cache_key = clicked_stock_isin
        if cache_key not in st.session_state.news_feed_per_stock:
            with st.spinner(f"Fetching news & filings for {clicked_stock_name}…"):
                st.session_state.news_feed_per_stock[cache_key] = news_fetch.get_combined_feed(
                    isin=clicked_stock_isin,
                    company_name=clicked_stock_name,
                    news_count=10,
                    bse_hours=72,
                )
        feed_items = st.session_state.news_feed_per_stock[cache_key]
    else:
        feed_items = st.session_state.news_feed_all

    # ── "Load more" state — extends the NEWS side further back in batches.
    # BSE stays hard-capped at 72h regardless (per the locked spec), so
    # load-more only re-fetches with a larger news_count. ──
    load_more_key = f"news_load_count_{clicked_stock_isin or 'ALL'}"
    if load_more_key not in st.session_state:
        st.session_state[load_more_key] = 10

    if not feed_items:
        st.info(
            "No news or BSE filings found in this window. "
            "Try 'Check for news updates' or select a different stock."
        )
    else:
        for item in feed_items:
            is_bse = item.get("_type") == "bse"
            title  = item.get("title", "Untitled")
            url    = item.get("url", "#")
            company = item.get("_company", "")
            dt     = item.get("_parsed_dt")
            ts_str = dt.strftime("%d %b %Y, %H:%M") if dt else "Unknown time"

            if is_bse:
                badge = '<span style="background:#3a7bd5;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600">BSE FILING</span>'
                source_label = item.get("category", "BSE")
            else:
                badge = '<span style="background:#00c896;color:#000;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600">NEWS</span>'
                source_label = item.get("source", "Unknown")

            st.markdown(f"""
            <div style="
                border: 1px solid #2e3a4a;
                border-radius: 10px;
                padding: 12px 16px;
                margin-bottom: 8px;
                background: #0e1a2b;
            ">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
                    <a href="{url}" target="_blank" style="
                        color: #e0e8f0; font-size: 0.92rem; font-weight: 600;
                        text-decoration: none; flex: 1; line-height: 1.4;
                    ">{title}</a>
                    <div style="white-space:nowrap">{badge}</div>
                </div>
                <div style="margin-top: 6px; font-size: 0.76rem; color: #607a99;">
                    {company}  ·  {source_label}  ·  {ts_str}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # "Load more" only makes sense in the per-stock view (portfolio-wide
        # already aggregates 10-per-stock x up to 39 stocks, which is plenty;
        # re-running that at a higher count would be very slow).
        if clicked_stock_isin:
            if st.button("Load more news"):
                st.session_state[load_more_key] += 10
                with st.spinner("Loading more news…"):
                    st.session_state.news_feed_per_stock[clicked_stock_isin] = news_fetch.get_combined_feed(
                        isin=clicked_stock_isin,
                        company_name=clicked_stock_name,
                        news_count=st.session_state[load_more_key],
                        bse_hours=72,
                    )
                st.rerun()


