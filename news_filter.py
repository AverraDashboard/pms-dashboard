"""
news_filter.py
===============
Filter 2 of the noise-reduction pipeline (Filter 1 lives in news_fetch.py
as the disambiguated search query).

Given a batch of headlines already fetched for ONE company, asks Claude to
judge which are genuinely about that company AND materially relevant to an
investor — then returns only those, in the original order.

Why batched, not one-call-per-headline: a single API call judging 10-20
headlines at once is far cheaper and faster than 10-20 separate calls, and
the judgment quality is the same or better since Claude sees the headlines
together (helps it calibrate "relevant" vs "noise" consistently).

Fails open, not closed: if the API key is missing, the call fails, or the
response can't be parsed, this returns the ORIGINAL unfiltered list rather
than an empty one. A relevance filter that silently hides all news because
of a transient API hiccup would be worse than no filter at all — Filter 1
(query disambiguation) is still doing useful work even if Filter 2 is down.
"""

import json
import os
import requests

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Looked up from environment — set as a GitHub Actions secret / Streamlit
# Cloud secret, NEVER hardcoded in this file. See README/setup notes for
# exactly how to set this on Streamlit Cloud (Settings -> Secrets).
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


def _get_api_key() -> str | None:
    # Try plain environment variable first (works for GitHub Actions, local testing)
    key = os.environ.get(API_KEY_ENV_VAR)
    if key:
        return key
    # Try Streamlit secrets (works when running inside Streamlit Cloud)
    try:
        import streamlit as st
        return st.secrets.get(API_KEY_ENV_VAR)
    except Exception:
        return None


def filter_relevant(headlines: list[dict], company_name: str) -> list[dict]:
    """
    headlines: list of dicts with at least a 'title' key (as returned by
               fetch_google_news in news_fetch.py)
    company_name: the holding these headlines were fetched for

    Returns the subset of `headlines` (same dicts, same order, just fewer)
    that Claude judges to be genuinely about this company AND material to
    an investor. On any failure, returns `headlines` unchanged.
    """
    if not headlines:
        return headlines

    api_key = _get_api_key()
    if not api_key:
        print(f"[news_filter] No {API_KEY_ENV_VAR} found — skipping relevance "
              f"filter for '{company_name}', showing unfiltered results")
        return headlines

    # Build a simple numbered list so Claude's response can reference
    # headlines by index rather than needing to echo text back (cheaper,
    # less error-prone than asking it to reproduce titles).
    numbered = "\n".join(f"{i+1}. {h.get('title', '')}" for i, h in enumerate(headlines))

    prompt = f"""You are filtering news headlines for an Indian equity portfolio manager who holds stock in "{company_name}".

For each headline below, decide:
- Is it genuinely ABOUT this specific company (not a different entity, person, place, or thing that happens to share the name)?
- IF it is about the company, is it the kind of news an investor would actually want to see (material business/financial/regulatory developments) — not pure noise (e.g. routine procedural filings with zero information content, or completely unrelated namesake stories)?

Headlines:
{numbered}

Respond with ONLY a JSON array of the headline numbers that pass BOTH checks, nothing else. No explanation, no markdown formatting, just the array.
Example response format: [1, 3, 4]
If none pass, respond: []"""

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        raw_text = "".join(text_blocks).strip()

        # Defensive cleanup in case the model wraps the array in markdown
        # fences despite being asked not to — cheap insurance against a
        # crash on an otherwise-working call.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`").replace("json", "", 1).strip()

        kept_indices = json.loads(raw_text)
        if not isinstance(kept_indices, list):
            raise ValueError(f"Expected a JSON array, got: {type(kept_indices)}")

        kept = [headlines[i - 1] for i in kept_indices if 1 <= i <= len(headlines)]
        print(f"[news_filter] '{company_name}': kept {len(kept)}/{len(headlines)} headlines after relevance check")
        return kept

    except Exception as e:
        print(f"[news_filter] Relevance filter failed for '{company_name}': {e} "
              f"— showing unfiltered results instead of failing the whole feed")
        return headlines


# ─────────────────────────────────────────────────────────────
# CLI test entrypoint
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_headlines = [
        {"title": "BlackBuck shares rally on Q4 logistics volume growth"},
        {"title": "Salman Khan blackbuck poaching case: court reserves verdict"},
        {"title": "BlackBuck Ltd announces new fleet partnership with Tata Motors"},
        {"title": "Rare blackbuck spotted in Gujarat wildlife sanctuary"},
    ]
    print("=== Testing relevance filter on BlackBuck/antelope ambiguity ===\n")
    print("Input headlines:")
    for h in test_headlines:
        print(f"  - {h['title']}")

    result = filter_relevant(test_headlines, "BlackBuck")

    print(f"\nKept {len(result)}/{len(test_headlines)}:")
    for h in result:
        print(f"  - {h['title']}")
