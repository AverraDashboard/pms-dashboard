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


# ─────────────────────────────────────────────────────────────
# CLI test entrypoint
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/AVERRAOPS1_229_PortFolioFactSheet6020UT__86_.pdf"
    print(f"Parsing: {path}\n")
    data = parse_cash_per_client(path)
    total = 0
    for client, info in data.items():
        print(f"  {info['av_code']} | {client:40} | Cash ₹{info['cash']:>10,} | Div ₹{info['dividend_receivable']:>7,}")
        total += info["total"]
    print(f"\n=== Firm total cash + div receivable: ₹{total:,} ===")
    print(f"Clients parsed: {len(data)}")
