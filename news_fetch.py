"""
news_fetch.py
=============
Piece 1: raw data fetchers for the portfolio news/leading-indicator system.

Two independent fetch functions:
  - fetch_bse_announcements(scripcode)   -> direct BSE filings for one stock
  - fetch_google_news(query)             -> news headlines for any search term
                                             (used for BOTH direct company news
                                             AND thesis-keyword spillover search)

Both are deliberately dumb and single-purpose. No relevance filtering happens
here — that's Piece 3 (news_filter.py). This file's only job is: given a
search term, return clean raw results.

NOTE: This module requires real internet access (bseindia.com, news.google.com).
It will NOT run inside the Claude sandbox used to build it (network is
allowlisted to package registries only). It WILL run on GitHub Actions and
Streamlit Cloud, same as the rest of the dashboard.
"""

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests

WATCHLIST_PATH = Path(__file__).parent / "watchlist.json"


# ─────────────────────────────────────────────────────────────
# WATCHLIST LOADING
# ─────────────────────────────────────────────────────────────
def load_watchlist() -> dict:
    """Load watchlist.json. Returns {} if missing/broken rather than crashing
    the whole pipeline — a malformed watchlist shouldn't take down Job 1."""
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("_comment", None)
        return data
    except Exception as e:
        print(f"[news_fetch] WARNING: could not load watchlist.json: {e}")
        return {}


def get_holding_by_isin(isin: str) -> tuple[str, dict] | tuple[None, None]:
    """
    Look up a watchlist entry by ISIN rather than display name.
    The dashboard's holdings table names (e.g. 'ETERNAL LTD', from the raw
    Nuvama Excel) don't reliably match watchlist.json's cleaned keys (e.g.
    'Eternal') — ISIN is the one field both sides share exactly, so all
    dashboard -> news_fetch lookups should go through this, not by name.

    Returns (company_name, config) or (None, None) if not found.
    """
    if not isin:
        return None, None
    wl = load_watchlist()
    isin_clean = isin.strip().upper()
    for name, config in wl.items():
        if (config.get("isin") or "").strip().upper() == isin_clean:
            return name, config
    return None, None


# ─────────────────────────────────────────────────────────────
# JOB 1a — BSE CORPORATE ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────
#
# IMPORTANT: BSE scrip lookup by company NAME (bse.getScripCode) is fuzzy
# and unreliable — it failed on "Orchid Pharma" even though that's the
# correct, well-known name. ISIN is unambiguous and every holding already
# has one (it's in your Nuvama Excel), so we build an ISIN -> scrip code
# map ONCE per run from BSE's full securities list, then look up by ISIN.
# This is slower on the first call but far more reliable than per-company
# name search, and only needs to happen once per script run, not once per
# stock.

_ISIN_TO_SCRIPCODE_CACHE: dict | None = None


def _build_isin_scripcode_map(bse) -> dict:
    """Fetch BSE's full active equity securities list (all groups) once,
    and build an ISIN -> scrip code lookup. Cached in-memory for the rest
    of this run so we don't re-fetch per stock."""
    global _ISIN_TO_SCRIPCODE_CACHE
    if _ISIN_TO_SCRIPCODE_CACHE is not None:
        return _ISIN_TO_SCRIPCODE_CACHE

    mapping = {}
    try:
        # group="" returns ALL groups (A, B, T, M, MS, Z, etc.), not just
        # the default Group A — needed since several holdings (Orchid,
        # ASM Tech, GNG, Dynamatic, Kwality, Timex) are smaller-cap names
        # that may not sit in Group A.
        #
        # Field names confirmed via diagnose_bse.py against the REAL BSE
        # response (2026-06-19): SCRIP_CD, Scrip_Name, ISIN_NUMBER,
        # Issuer_Name, GROUP, Status, Segment, NSURL, etc. — all
        # uppercase/mixed, not the lowercase guesses used in the first
        # version of this file.
        securities = bse.listSecurities(group="")
        for s in securities:
            isin = s.get("ISIN_NUMBER")
            code = s.get("SCRIP_CD")
            url  = s.get("NSURL", "")
            if isin and code:
                mapping[isin.strip().upper()] = {
                    "scripcode": str(code).strip(),
                    "url": url,
                }
    except Exception as e:
        print(f"[news_fetch] Could not build BSE ISIN->scripcode map: {e}")

    _ISIN_TO_SCRIPCODE_CACHE = mapping
    print(f"[news_fetch] BSE securities map built: {len(mapping)} ISINs resolved")
    return mapping


def fetch_bse_announcements(isin: str, company_name: str, days_back: int = 2) -> list[dict]:
    """
    Fetch recent BSE corporate announcements for one company, looked up by
    ISIN (reliable) rather than company name (fuzzy, can silently fail).

    Returns a list of dicts: [{title, category, date, url}, ...]
    Empty list on any failure — callers should treat that as "nothing found",
    not as an error, since absence of filings is the normal case most days.
    """
    from bse import BSE  # imported here so this module can still be parsed/tested
                           # even in environments where `bse` package isn't installed

    if not isin:
        print(f"[news_fetch] No ISIN provided for '{company_name}' — skipping BSE lookup")
        return []

    results = []
    try:
        with BSE(download_folder="./_bse_tmp") as bse:
            isin_map = _build_isin_scripcode_map(bse)
            entry = isin_map.get(isin.strip().upper())

            if not entry:
                print(f"[news_fetch] No BSE scripcode found for ISIN {isin} ('{company_name}') — "
                      f"may be a recent IPO, ETF, or BSE-only/unlisted name not in the active equity list")
                return []

            code = entry["scripcode"]
            bse_url = entry.get("url") or f"https://www.bseindia.com/stock-share-price/x/x/{code}/"

            to_date = datetime.now()
            from_date = to_date - timedelta(days=days_back)

            data = bse.announcements(
                scripcode=code,
                from_date=from_date,
                to_date=to_date,
            )
            rows = data.get("Table", [])

            for row in rows:
                results.append({
                    "title":    row.get("NEWSSUB") or row.get("HEADLINE") or "Untitled announcement",
                    "category": row.get("CATEGORYNAME", ""),
                    "date":     row.get("NEWS_DT") or row.get("DissemDT") or "",
                    "url":      bse_url,
                    "source":   "BSE Filing",
                    "scripcode": code,
                })
    except Exception as e:
        print(f"[news_fetch] BSE announcements fetch failed for '{company_name}' (ISIN {isin}): {e}")
        return []

    return results


# ─────────────────────────────────────────────────────────────
# JOB 1b / JOB 2 — GOOGLE NEWS RSS (works for company name OR thesis keyword)
# ─────────────────────────────────────────────────────────────
def _build_company_search_query(company_name: str) -> str:
    """
    Filter 1 (cheap, fast): disambiguate company-name searches so they don't
    collide with unrelated uses of the same word.

    Real example that motivated this: 'BlackBuck' (your logistics holding)
    is ALSO the name of an antelope species, and pulled wildlife/Salman-Khan
    news instead of company news. Appending finance-context terms steers
    Google News toward the company, not the word.

    This only applies to direct company-name searches (Job 1). Thesis
    keywords (Job 2, e.g. 'oral GLP-1') are already specific phrases and
    don't need this treatment — adding it there would over-narrow and
    risk missing genuine spillover news.
    """
    # Quote the company name so multi-word names are searched as a phrase,
    # not as separate OR'd words (avoids e.g. "Blue" OR "Jet" OR "Healthcare"
    # matching unrelated blue/jet/healthcare articles).
    return f'"{company_name}" (stock OR shares OR NSE OR BSE OR Ltd)'


def fetch_google_news(query: str, max_results: int = 8, region: str = "IN") -> list[dict]:
    """
    Fetch recent news headlines for any search query via Google News RSS.
    No API key needed. Same function serves:
      - Job 1: query = company name  -> direct news
      - Job 2: query = thesis keyword -> spillover news

    Returns list of dicts: [{title, source, published, url}, ...]
    """
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search?q={encoded_query}"
        f"&hl=en-{region}&gl={region}&ceid={region}:en"
    )

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AverraNewsBot/1.0)"}

    results = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = root.findall(".//item")[:max_results]
        for item in items:
            title = item.findtext("title", default="")
            link = item.findtext("link", default="")
            pub_date = item.findtext("pubDate", default="")
            source_el = item.find("source")
            source = source_el.text if source_el is not None else "Unknown"

            # Google News titles often come as "Headline - Source" — strip the
            # trailing " - Source" since we already have source separately
            if title.endswith(f" - {source}"):
                title = title[: -(len(source) + 3)]

            results.append({
                "title":     title.strip(),
                "source":    source,
                "published": pub_date,
                "url":       link,
                "query":     query,  # keep track of which search produced this,
                                       # useful for debugging Job 2 keyword noise
            })
    except Exception as e:
        print(f"[news_fetch] Google News fetch failed for query '{query}': {e}")
        return []

    return results


# ─────────────────────────────────────────────────────────────
# TIMESTAMP NORMALIZATION — needed to merge-sort News + BSE together
# ─────────────────────────────────────────────────────────────
def _parse_timestamp(raw: str) -> datetime | None:
    """
    Both sources give different date formats AND different timezone
    handling:
      - Google News pubDate: 'Thu, 18 Jun 2026 09:30:00 GMT'  (RFC 822,
        parses as TIMEZONE-AWARE)
      - BSE NEWS_DT:          '2026-06-12T12:57:49.567'        (ISO-ish,
        parses as TIMEZONE-NAIVE — no offset info)
    Python cannot compare aware and naive datetimes directly, so we
    normalize everything to naive (strip tzinfo) for sorting purposes.
    This is a small approximation (GMT vs IST offset isn't corrected for)
    but is fine for "what's most recent" ordering — exact-minute precision
    across timezones isn't needed for a news feed.

    Returns None if parsing fails — caller should treat that item as
    "unknown time" and sort it last, not crash the whole feed.
    """
    if not raw:
        return None
    raw = raw.strip()
    # Try RFC 822 (Google News) first
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        pass
    # Try ISO format (BSE) — handle variable fractional-second precision
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────
# ORCHESTRATION — pull everything for one holding
# ─────────────────────────────────────────────────────────────
def fetch_all_for_holding(name: str, config: dict) -> dict:
    """
    Pull BSE filings + direct news + thesis-keyword spillover news for ONE
    holding. Returns a dict ready to hand to Piece 3 (relevance filter).

    `config` is the watchlist.json entry for this holding.
    """
    direct_news = fetch_google_news(name, max_results=8)
    bse_filings = fetch_bse_announcements(config.get("isin", ""), name, days_back=2)

    spillover_news = []
    for kw in config.get("thesis_keywords", []):
        spillover_news.extend(fetch_google_news(kw, max_results=4))
        time.sleep(0.5)  # be polite to Google News — avoid hammering in a tight loop

    return {
        "company":          name,
        "fetched_at":       datetime.now().isoformat(),
        "direct_news":      direct_news,
        "bse_filings":      bse_filings,
        "spillover_news":   spillover_news,
    }


def fetch_all_holdings() -> dict:
    """Run fetch_all_for_holding() across every entry in watchlist.json.
    This is the single function the daily GitHub Action / manual refresh
    button calls."""
    watchlist = load_watchlist()
    all_results = {}
    for name, config in watchlist.items():
        print(f"[news_fetch] Fetching: {name}")
        all_results[name] = fetch_all_for_holding(name, config)
        time.sleep(1)  # stay polite across companies too
    return all_results


# ─────────────────────────────────────────────────────────────
# DASHBOARD COMBINED FEED
# ─────────────────────────────────────────────────────────────
# Implements the exact rule set agreed for the dashboard feed:
#   - News: always the N most recent items, NOT time-boxed (could be
#     hours or weeks old — doesn't matter, just "give me the latest N").
#     "Load more" extends N further back in batches.
#   - BSE filings: strictly capped to the last 72 hours. No backfill —
#     if there's nothing in that window, show nothing for BSE.
#   - Both merged into ONE list, sorted by actual timestamp, newest first.
#
# This is intentionally separate from fetch_all_for_holding() above
# (which is the older, simpler Job1+Job2 puller) because the dashboard's
# display rules are specific and shouldn't leak into the general-purpose
# fetch logic other callers (e.g. a future GitHub Action) might use.

BSE_WINDOW_HOURS = 72


def _tag_and_parse(items: list[dict], item_type: str) -> list[dict]:
    """Attach a type label and a parsed datetime to each item, for sorting."""
    out = []
    for it in items:
        raw_ts = it.get("published") if item_type == "news" else it.get("date")
        parsed = _parse_timestamp(raw_ts)
        out.append({**it, "_type": item_type, "_parsed_dt": parsed})
    return out


def get_combined_feed(
    isin: str | None,
    company_name: str | None,
    news_count: int = 10,
    bse_hours: int = BSE_WINDOW_HOURS,
    apply_relevance_filter: bool = True,
) -> list[dict]:
    """
    Build the combined News + BSE feed for ONE stock, per the dashboard's
    locked rules. Pass isin=None / company_name=None style is not
    supported here — this is always scoped to one company; the "all 39
    holdings" view is built by calling this once per holding and merging
    (see get_portfolio_wide_feed below).

    Noise reduction (two filters, see news_filter.py for Filter 2):
      Filter 1 (here): search query is disambiguated with finance-context
        terms (e.g. 'BlackBuck' -> '"BlackBuck" (stock OR shares OR NSE...)')
        so unrelated same-name results (the antelope, not the logistics co.)
        mostly don't show up in the first place.
      Filter 2 (news_filter.py, applied below if apply_relevance_filter):
        whatever Filter 1 didn't catch gets judged by Claude for genuine
        relevance + materiality before reaching the dashboard.

    We over-fetch (request more than news_count) BEFORE filtering, since
    Filter 2 will discard some — without this, a stock could show fewer
    than news_count items even when more real news exists.

    Returns a flat, sorted (newest first) list of dicts, each tagged with
    '_type' ('news' or 'bse') so the UI can style them differently.
    """
    fetch_count = news_count * 2 if apply_relevance_filter else news_count
    search_query = _build_company_search_query(company_name) if company_name else company_name
    news_raw = fetch_google_news(search_query, max_results=fetch_count)
    bse_raw  = fetch_bse_announcements(isin, company_name, days_back=max(1, bse_hours // 24 + 1))

    if apply_relevance_filter and news_raw:
        try:
            import news_filter
            news_raw = news_filter.filter_relevant(news_raw, company_name)
        except Exception as e:
            print(f"[news_fetch] Relevance filter unavailable/failed for '{company_name}': {e} "
                  f"— showing unfiltered results instead of failing the whole feed")

    news_raw = news_raw[:news_count]  # trim back down after filtering

    news_tagged = _tag_and_parse(news_raw, "news")

    # BSE: filter down to the strict hour window (fetch_bse_announcements
    # works in whole days, so we re-filter precisely to hours here)
    cutoff = datetime.now() - timedelta(hours=bse_hours)
    bse_tagged = [
        b for b in _tag_and_parse(bse_raw, "bse")
        if b["_parsed_dt"] is not None and b["_parsed_dt"] >= cutoff
    ]

    combined = news_tagged + bse_tagged
    # Sort newest first; items with unparseable timestamps sort last
    combined.sort(key=lambda x: x["_parsed_dt"] or datetime.min, reverse=True)

    for item in combined:
        item["_company"] = company_name
        item["_isin"] = isin

    return combined


def get_portfolio_wide_feed(news_count: int = 10, bse_hours: int = BSE_WINDOW_HOURS) -> list[dict]:
    """
    Build the default 'all holdings' dashboard feed: loops every entry in
    watchlist.json, gets each one's combined feed, and merges everything
    into one big recency-sorted list spanning the whole portfolio.

    NOTE: this is the expensive call — up to 39 stocks x (1 news fetch +
    1 BSE fetch + N thesis-keyword fetches). Expect this to take real time
    (tens of seconds) on a full run. The dashboard should cache this in
    st.session_state and only re-run it on an actual page reload, not on
    every interaction — see app.py for how that's wired.
    """
    watchlist = load_watchlist()
    all_items = []
    for name, config in watchlist.items():
        items = get_combined_feed(
            isin=config.get("isin"),
            company_name=name,
            news_count=news_count,
            bse_hours=bse_hours,
        )
        all_items.extend(items)
        time.sleep(0.3)  # stay polite across companies

    all_items.sort(key=lambda x: x["_parsed_dt"] or datetime.min, reverse=True)
    return all_items


# ─────────────────────────────────────────────────────────────
# CLI test entrypoint — run this file directly to sanity-check fetchers
# against ONE company before running the full watchlist.
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    test_company = sys.argv[1] if len(sys.argv) > 1 else "Orchid Pharma"
    wl = load_watchlist()
    test_isin = wl.get(test_company, {}).get("isin", "")

    print(f"=== Testing fetchers for: {test_company} (ISIN: {test_isin or 'not found in watchlist.json'}) ===\n")

    print("--- Direct Google News ---")
    news = fetch_google_news(test_company, max_results=5)
    for n in news:
        print(f"  [{n['published']}] {n['title']} ({n['source']})")

    print("\n--- BSE Announcements (last 30 days) ---")
    filings = fetch_bse_announcements(test_isin, test_company, days_back=30)
    for f in filings:
        print(f"  [{f['date']}] {f['title']} ({f['category']})")

    print(f"\nFound {len(news)} news items, {len(filings)} BSE filings for {test_company}.")

    # Sanity check: large, frequently-filing names almost always have SOME
    # announcement in a 30-day window. If THIS also comes back empty, the
    # problem is mechanical (code/connection), not "this stock is quiet".
    if not filings:
        print("\n--- Sanity check: ICICI Bank (large-cap, files frequently) ---")
        icici_isin = wl.get("ICICI Bank", {}).get("isin", "INE090A01021")
        sanity = fetch_bse_announcements(icici_isin, "ICICI Bank", days_back=30)
        print(f"ICICI Bank filings in last 30 days: {len(sanity)}")
        for f in sanity[:5]:
            print(f"  [{f['date']}] {f['title']} ({f['category']})")
        if sanity:
            print("\n-> BSE mechanism WORKS. Orchid likely just has no recent filings — that's normal.")
        else:
            print("\n-> Even ICICI shows zero. Something is still mechanically broken — send this output back.")
