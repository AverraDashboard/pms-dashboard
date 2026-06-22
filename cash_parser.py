"""
cash_parser.py
===============
Parses the Nuvama PortFolioFactSheet PDF for per-client cash holdings.

Why this exists:
  The standard Nuvama holding statement Excel (the one app.py already
  reads) shows only stock positions — it OMITS each client's cash
  balance and dividend/interest receivable. So the dashboard's
  Excel-only view UNDERSTATES true AUM, and overstates every stock's
  % of portfolio.

  The PortFolioFactSheet PDF, sent separately by Nuvama, has the cash
  info per client. This module pulls only what the Excel is missing
  ("Cash" + "Dividend / Interest receivable" rows from each client's
  Portfolio Holdings table) and exposes it for app.py to combine with
  the Excel.

Critical design choices:
  - LIQUIDBEES (Nippon India ETF Liquid BeES) is NOT treated as cash
    here, by explicit user direction. It stays in the Excel as a
    regular stock. Only the two named rows (Cash, Dividend/Interest
    receivable) feed the cash bucket.
  - Client names from the PDF were verified to match the Excel-derived
    Client Name strings exactly (case, spacing, spelling — all 21
    clients align). Join is by exact name match. If a future PDF
    introduces a name variant we'll see it as a "missing client" in
    the returned dict, which app.py logs visibly rather than silently
    dropping.
  - Failure mode is "skip cash, show stock-only AUM with a warning" —
    never crash the dashboard. The cash feature is additive; an
    unparseable PDF should never break the whole app.
"""

import re
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


# Account header line: "Account: 22910001 - REKHA KISHORE MEHTA - AV0001"
_ACCOUNT_RE = re.compile(
    r"Account:\s*(?P<account>\d+)\s*-\s*(?P<name>[^-\n]+?)\s*-\s*(?P<av>AV\d+)"
)

# "Inception Date: 14/01/2026"  (DD/MM/YYYY)
_INCEPTION_RE = re.compile(r"Inception Date:\s*(\d{2}/\d{2}/\d{4})")


def _parse_money(value) -> int:
    """Parse a money cell like '1,952' -> 1952. Returns 0 on failure rather
    than raising — keeps one bad cell from killing the whole page."""
    if value is None:
        return 0
    s = str(value).replace(",", "").strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _is_cash_row(security: str | None, sector: str | None) -> bool:
    """A row in the Portfolio Holdings table is 'cash' if its Security
    column is literally 'Cash' OR its Sector says 'Cash and Equivalent'.
    LIQUIDBEES has sector 'Cash and Equivalent' too BUT we exclude it by
    name, per the user's instruction to keep it classified as a stock."""
    sec = (security or "").strip()
    sector_s = (sector or "").strip().lower()
    if "liquid bee" in sec.lower():
        return False  # explicit user direction: LIQUIDBEES stays a stock
    if sec.strip().lower() == "cash":
        return True
    return False  # NB: don't include sector-only matches, too risky


def _is_dividend_receivable_row(security: str | None, sector: str | None) -> bool:
    """The dividend/interest receivable row — small accrued balances that
    behave like cash for return purposes."""
    sec = (security or "").strip().lower()
    if "dividend" in sec and "interest" in sec and "receivable" in sec:
        return True
    # Sometimes the Security field is just "Dividend / Interest receivable"
    return sec == "dividend / interest receivable"


def _parse_pct(value) -> float | None:
    """Parse a Performance(TWRR) cell like '15.9%' or '-1.31%' or '-' -> float or None.
    Handles the awkward '- -' collapsed-cell case where pdfplumber merges
    multiple missing values into a single string."""
    if value is None:
        return None
    s = str(value).strip().replace("%", "").strip()
    if not s or s in ("-", "—", "- -", "-  -"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_since_inception_returns(tables) -> tuple[float | None, float | None]:
    """From a page's tables, find the Performance(TWRR) table and pull the
    'Since' (last) column values for Portfolio and BSE 500 rows.

    Returns (portfolio_since_pct, bse500_since_pct). Either or both may be
    None if missing/unparseable — caller should handle.

    Why 'last value' instead of position-4: when a young client has no 1m,
    3m, or 1y data (all "-"), pdfplumber sometimes collapses empty cells
    so the row has fewer than 4 percentage cells visible. The 'Since'
    value is reliably the LAST non-empty cell of the row regardless.
    """
    portfolio_since = None
    bse_since = None
    for table in tables:
        # Identify Performance(TWRR) table by its header row
        is_perf_table = False
        for row in table:
            row_text = " ".join(str(c) for c in row if c)
            if "Performance(TWRR)" in row_text or "TWRR" in row_text:
                is_perf_table = True
                break
        if not is_perf_table:
            continue
        # Find Portfolio and BSE rows in this table
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(c) for c in row if c)
            # The "Since" value is the last non-empty cell of the row
            non_empty = [c for c in row if c is not None and str(c).strip() != ""]
            if not non_empty:
                continue
            last_cell = non_empty[-1]
            since_val = _parse_pct(last_cell)
            # Identify which row this is
            if "Portfolio" in row_text and "BSE" not in row_text and "Holdings" not in row_text:
                if portfolio_since is None:  # take first match only
                    portfolio_since = since_val
            elif "BSE" in row_text or "Return Index" in row_text:
                if bse_since is None:
                    bse_since = since_val
    return portfolio_since, bse_since


def parse_cash_per_client(pdf_path: str | Path) -> dict[str, dict]:
    """
    Extract per-client cash + dividend receivable from the Nuvama PDF.

    Returns a dict keyed by UPPERCASE client name (matching the Excel's
    Client Name format exactly), each entry containing:
        {'cash': int, 'dividend_receivable': int, 'av_code': str, 'account': str}

    Returns {} on any failure (missing file, missing pdfplumber, parse
    error) — caller in app.py should handle this gracefully.
    """
    if not PDFPLUMBER_AVAILABLE:
        print("[cash_parser] pdfplumber not installed — skipping cash parse")
        return {}

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"[cash_parser] PDF not found at {pdf_path} — proceeding without cash data")
        return {}

    out = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                m = _ACCOUNT_RE.search(text)
                if not m:
                    # Some PDFs may have summary/cover pages without an
                    # Account header — skip them silently, normal case.
                    continue
                account = m.group("account")
                client_name = m.group("name").strip().upper()
                av_code = m.group("av")

                cash_inr = 0
                div_inr = 0

                for table in page.extract_tables():
                    for row in table:
                        # Portfolio Holdings table has 5 cols:
                        # [Sr, Security, Sector, Mkt Value, %Assets]
                        if not row or len(row) < 5:
                            continue
                        _, sec, sector, mkt, _ = row[:5]
                        if _is_cash_row(sec, sector):
                            cash_inr += _parse_money(mkt)
                        elif _is_dividend_receivable_row(sec, sector):
                            div_inr += _parse_money(mkt)

                # If a page had an Account header but yielded zero cash AND
                # zero div, that's worth flagging — could mean the table
                # structure changed. Don't drop it though; record zeros.
                out[client_name] = {
                    "cash": cash_inr,
                    "dividend_receivable": div_inr,
                    "total": cash_inr + div_inr,
                    "av_code": av_code,
                    "account": account,
                }
    except Exception as e:
        print(f"[cash_parser] Parse failed: {e} — proceeding without cash data")
        return {}

    return out


def get_firm_total_cash(pdf_path: str | Path) -> int:
    """Quick helper: total cash + div receivable across every client.
    Returns 0 if PDF can't be parsed."""
    data = parse_cash_per_client(pdf_path)
    return sum(d["total"] for d in data.values())


def parse_performance_per_client(pdf_path: str | Path) -> dict[str, dict]:
    """
    Extract per-client TWRR performance + inception date from the Nuvama PDF.

    These figures act as the ANCHOR for the dashboard's live-adjusted
    return columns. Each time a new PDF is uploaded, these reset to the
    PDF's reported values; between PDF uploads, the dashboard drifts them
    using daily stock and index moves (computed live, not from PDF).

    Returns dict keyed by UPPERCASE client name (matching the Excel's
    Client Name format), each entry containing:
        {
            'inception_date': datetime,    # parsed from DD/MM/YYYY
            'inception_date_str': '14/01/2026',
            'portfolio_since_inception': 15.9,  # percentage, can be negative
            'bse500_since_inception': -1.31,
            'av_code': 'AV0001',
            'account': '22910001',
        }

    Returns {} on any failure. Caller must handle missing entries (e.g.
    a brand-new client in the Excel that doesn't appear in the PDF yet).
    """
    if not PDFPLUMBER_AVAILABLE:
        print("[cash_parser] pdfplumber not installed — skipping performance parse")
        return {}

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"[cash_parser] PDF not found at {pdf_path}")
        return {}

    out = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                m = _ACCOUNT_RE.search(text)
                if not m:
                    continue
                account = m.group("account")
                client_name = m.group("name").strip().upper()
                av_code = m.group("av")

                # Inception date
                inc_match = _INCEPTION_RE.search(text)
                if not inc_match:
                    # Page has account header but no parseable inception —
                    # skip rather than guess a date
                    continue
                inception_str = inc_match.group(1)
                try:
                    inception_dt = datetime.strptime(inception_str, "%d/%m/%Y")
                except ValueError:
                    continue

                # Performance numbers from the TWRR table
                tables = page.extract_tables()
                port_since, bse_since = _extract_since_inception_returns(tables)

                out[client_name] = {
                    "inception_date": inception_dt,
                    "inception_date_str": inception_str,
                    "portfolio_since_inception": port_since,
                    "bse500_since_inception": bse_since,
                    "av_code": av_code,
                    "account": account,
                }
    except Exception as e:
        print(f"[cash_parser] Performance parse failed: {e}")
        return {}

    return out


def get_pdf_as_of_date(pdf_path: str | Path) -> datetime | None:
    """Extract the 'As of: DD/MM/YYYY' date from the PDF header.

    This is the date the PDF was generated for, and serves as the anchor
    point: the dashboard's live-adjusted returns reflect movement from
    this date forward, on top of the PDF-reported figures. Returns None
    if the date can't be found/parsed.
    """
    if not PDFPLUMBER_AVAILABLE:
        return None
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            m = re.search(r"As of:\s*(\d{2}/\d{2}/\d{4})", first_page_text)
            if m:
                return datetime.strptime(m.group(1), "%d/%m/%Y")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# CLI test entrypoint
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/AVERRAOPS1_229_PortFolioFactSheet6020UT__86_.pdf"
    print(f"Parsing: {path}\n")
    as_of = get_pdf_as_of_date(path)
    print(f"PDF 'As of' date: {as_of}\n")

    print("=" * 60)
    print("CASH PER CLIENT")
    print("=" * 60)
    cash_data = parse_cash_per_client(path)
    total = 0
    for client, info in cash_data.items():
        print(f"  {info['av_code']} | {client[:35]:35} | Cash ₹{info['cash']:>10,} | Div ₹{info['dividend_receivable']:>7,}")
        total += info["total"]
    print(f"  → Firm total: ₹{total:,}")
    print(f"  → Clients: {len(cash_data)}")

    print()
    print("=" * 60)
    print("PERFORMANCE PER CLIENT")
    print("=" * 60)
    perf_data = parse_performance_per_client(path)
    for client, info in perf_data.items():
        print(f"  {info['av_code']} | {client[:30]:30} | Inc {info['inception_date_str']} | "
              f"Port {info['portfolio_since_inception']!s:>7} | BSE {info['bse500_since_inception']!s:>7}")
    print(f"  → Clients: {len(perf_data)}")

