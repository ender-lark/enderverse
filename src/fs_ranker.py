#!/usr/bin/env python3
"""
Fundstrat Inbox Ranker — Sprint Launcher C-build (v1.0)

Scans Fundstrat Inbox entries for ticker + thesis-keyword mentions,
ranks by portfolio relevance.

Approach (per operator choice "both"):
  1. WHITELIST PATH: held + watchlist tickers always match (high confidence)
  2. PATTERN PATH: $cashtag, "Tickers in Report:" headers, stock-context
     verbs (buy/sell/add/trim TICKER, TICKER stock/shares/calls/puts)
  3. BLACKLIST: 200+ common all-caps abbreviations (CEO, AI, USD, ETF, GDP,
     etc.) filtered out so bare-caps pattern doesn't false-fire
  4. THESIS PATH: per-position keyword match catches Tom Lee-style macro
     notes that move held positions without naming them (BMNR moves on
     "scarce" + "stablecoin" + "CLARITY"; LEU moves on "uranium"; etc.)

Output: ranked list, tier-bucketed (HELD > WATCHLIST > THESIS-HELD >
NAMED-NOT-HELD > MACRO).

Usage:
    python fs_ranker.py < inbox_dump.txt
    python fs_ranker.py --json < entries.json
    
Or import:
    from fs_ranker import rank_entries
"""

import re
import json
import sys
from pathlib import Path
from collections import defaultdict

CONFIG_PATH = Path(__file__).parent / "fs_holdings.json"

# ============================================================
# Config load
# ============================================================
with open(CONFIG_PATH) as f:
    _cfg = json.load(f)

HELD = set(_cfg["held"])
WATCHLIST = set(_cfg["watchlist"])
THESIS_KEYWORDS = _cfg["thesis_keywords"]
MACRO_THEMES = _cfg.get("macro_themes", {})
COMPANY_ALIASES = _cfg.get("company_aliases", {})

# ============================================================
# Blacklist (common all-caps that aren't tickers)
# ============================================================
BLACKLIST = {
    # Generic short words
    "A","I","AT","ON","OR","IS","IT","BE","DO","GO","NO","OK",
    "AN","AS","BY","IF","IN","OF","TO","UP","US","WE","SO","HE",
    "MY","ME","HIS","HER","OUR","ALL","NEW","OLD","NOW","ONE","TWO",
    "THE","FOR","AND","BUT","NOT","WAS","ARE","CAN","HAS","HAD","WHO",
    # Finance generic
    "AI","ML","ETF","IPO","MNA","LBO","PE","VC","GP","LP",
    "EPS","EBIT","EBITDA","PEG","ROE","ROI","ROIC","CAPM",
    "AUM","NAV","GAV","FFO","DCF","WACC","IRR","TAM","SAM","SOM",
    "ATH","ATL","ADR","OTC","BPS","QOQ","YOY","MOM",
    "DD","EOD","BOY","EOY","YTD","MTD","QTD","FY","Q1","Q2","Q3","Q4",
    "1Q","2Q","3Q","4Q","H1","H2","1H","2H",
    "OW","UW","BUY","SELL","HOLD","HOLDS","HELD","OWN","OWNS",
    "BULL","BEAR","LONG","SHORT","PUT","PUTS","CALL","CALLS",
    "DIO","GM","GMS","CAPEX","OPEX","FCF","OCF","RSU","ESG",
    # Roles
    "CEO","CFO","COO","CTO","CIO","CMO","CHRO","CSO",
    # Macro / orgs
    "GDP","CPI","PPI","PCE","PMI","ISM","JOLTS","NFP","FOMC",
    "FED","ECB","BOJ","BOE","PBOC","RBA","RBI","BOC","SNB",
    "SEC","FINRA","FDIC","OCC","CFTC","DOJ","FBI","CIA","DOD",
    "USDA","FDA","FAA","FCC","FTC","OECD","IMF","NATO","WTO",
    "UN","UK","EU","DM","APAC","EMEA","LATAM","MENA","ICE",
    # Currencies / FX
    "USD","EUR","JPY","GBP","CHF","CAD","AUD","NZD","CNY","CNH",
    "HKD","INR","KRW","BRL","MXN","RUB","TRY","ZAR","SGD","DXY",
    "FX","EM",
    # Indices
    "SPX","NDX","RUT","DJX","VIX",
    # Media / pubs
    "WSJ","NYT","FT","BBC","CNN","CNBC","NPR","REU","GUA","BBG",
    "MSNBC","FOX","ABC","AP","AFP","PR","PSA",
    # Tech generic
    "API","URL","URI","UI","UX","OS","IOS","IOT","VR","AR",
    "CPU","GPU","TPU","ASIC","FPGA","DRAM","HBM","SSD","HDD",
    "RAM","ROM","USB","HDMI","AWS","GCP","SAAS","PAAS",
    "IAAS","B2B","B2C","D2C","DTC","SLA","KPI","OKR","MVP",
    # Misc
    "TLDR","FAQ","ASAP","FYI","BTW","IMO","IMHO","TBD","NA","NM","NS",
    "TBA","ETA","AKA","RT","PM","AM","ET","PT","MT","CT",
    "EST","PST","MST","CST","GMT","UTC",
    # Time abbrev
    "JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC",
    "MON","TUE","WED","THU","FRI","SAT","SUN",
}
BLACKLIST |= set(_cfg.get("blacklist_extra", []))

# ============================================================
# Patterns
# ============================================================
RE_CASHTAG       = re.compile(r'\$([A-Z]{1,5}(?:\.[A-Z])?)\b')
RE_TICKER_HEADER = re.compile(
    r'Tickers?(?:\s+in\s+(?:this\s+)?(?:Report|Video|Note))?[\s:]+'
    r'((?:[A-Z]{1,5}(?:\.[A-Z])?[\s,\+\-\d.%▲▼]*){1,20})',
    re.IGNORECASE
)
RE_VERB_TICKER   = re.compile(
    r'\b(?:buy|sell|add|trim|long|short|own|hold|bought|sold|owns|holds)\s+'
    r'([A-Z]{2,5}(?:\.[A-Z])?)\b'
)
RE_TICKER_NOUN   = re.compile(
    r'\b([A-Z]{2,5}(?:\.[A-Z])?)\s+'
    r'(?:stock|shares|equity|calls?|puts?|earnings|reported|announced)'
)
RE_BARE_CAPS     = re.compile(r'\b([A-Z]{2,5}(?:\.[A-Z])?)\b')


# ============================================================
# Extraction
# ============================================================
def extract_tickers(text):
    """Returns dict: ticker -> {'confidence': str, 'sources': set}."""
    hits = defaultdict(lambda: {"confidence": "low", "sources": set()})

    def upgrade(t, conf, src):
        rank = {"low": 0, "medium": 1, "high": 2}
        if rank[conf] > rank[hits[t]["confidence"]]:
            hits[t]["confidence"] = conf
        hits[t]["sources"].add(src)

    # 1. Cashtags = HIGH
    for m in RE_CASHTAG.finditer(text):
        t = m.group(1).upper()
        if t not in BLACKLIST:
            upgrade(t, "high", "cashtag")

    # 2. Explicit "Tickers in Report:" headers = HIGH
    for m in RE_TICKER_HEADER.finditer(text):
        for tm in re.findall(r'\b([A-Z]{1,5}(?:\.[A-Z])?)\b', m.group(1)):
            t = tm.upper()
            if t not in BLACKLIST:
                upgrade(t, "high", "ticker_header")

    # 3. Verb + TICKER, TICKER + stock-noun = MEDIUM
    for m in RE_VERB_TICKER.finditer(text):
        t = m.group(1).upper()
        if t not in BLACKLIST:
            upgrade(t, "medium", "verb_context")
    for m in RE_TICKER_NOUN.finditer(text):
        t = m.group(1).upper()
        if t not in BLACKLIST:
            upgrade(t, "medium", "noun_context")

    # 4. Bare caps — ONLY count if whitelisted (held or watchlist)
    for m in RE_BARE_CAPS.finditer(text):
        t = m.group(1).upper()
        if t in BLACKLIST:
            continue
        if t in HELD or t in WATCHLIST:
            upgrade(t, "high", "whitelist_match")

    # 5. Company-name aliases — case-insensitive prose mentions
    text_lower = text.lower()
    for ticker, aliases in COMPANY_ALIASES.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                upgrade(ticker, "high", "company_alias")
                break

    return dict(hits)


def extract_thesis_hits(text):
    """Returns dict: ticker -> [matched_keywords]. Catches macro notes
    that move held positions without naming them."""
    text_lower = text.lower()
    hits = {}
    for ticker, keywords in THESIS_KEYWORDS.items():
        matched = [kw for kw in keywords if kw.lower() in text_lower]
        if matched:
            hits[ticker] = matched
    return hits


def extract_macro_themes(text):
    """Returns list of matched macro-theme labels."""
    text_lower = text.lower()
    matched = []
    for theme, keywords in MACRO_THEMES.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(theme)
    return matched


# ============================================================
# Ranking
# ============================================================
def rank_entry(entry):
    text = f"{entry.get('subject','')}\n{entry.get('body','')}"
    tickers = extract_tickers(text)
    thesis = extract_thesis_hits(text)
    themes = extract_macro_themes(text)

    held_direct      = sorted(t for t in tickers if t in HELD)
    watchlist_direct = sorted(t for t in tickers if t in WATCHLIST and t not in HELD)
    unknown_direct   = sorted(t for t in tickers if t not in HELD and t not in WATCHLIST)
    thesis_held      = sorted(t for t in thesis if t in HELD and t not in held_direct)

    # Score: direct held=10, thesis-held=5, watchlist=3, unknown=1
    score = (
        len(held_direct) * 10 +
        len(thesis_held) * 5 +
        len(watchlist_direct) * 3 +
        min(len(unknown_direct), 3)
    )

    # Tier
    if held_direct:
        tier = "HELD"
    elif thesis_held:
        tier = "THESIS-HELD"
    elif watchlist_direct:
        tier = "WATCHLIST"
    elif unknown_direct:
        tier = "NAMED-NOT-HELD"
    else:
        tier = "MACRO"

    return {
        "tier": tier,
        "score": score,
        "held_hits": held_direct,
        "thesis_hits": {t: thesis[t] for t in thesis_held},
        "watchlist_hits": watchlist_direct,
        "unknown_hits": unknown_direct,
        "macro_themes": themes,
        "ticker_details": tickers,
        "subject": entry.get("subject", ""),
        "timestamp": entry.get("timestamp", ""),
        "analyst": entry.get("analyst", ""),
    }


def rank_entries(entries):
    tier_order = {"HELD":0, "THESIS-HELD":1, "WATCHLIST":2, "NAMED-NOT-HELD":3, "MACRO":4}
    ranked = [rank_entry(e) for e in entries]
    return sorted(ranked, key=lambda r: (tier_order[r["tier"]], -r["score"], r["timestamp"]))


def format_for_sprint(ranked, max_show=5):
    """Mobile-friendly sprint output."""
    lines = []
    for i, r in enumerate(ranked[:max_show], 1):
        head = f"{i}. [{r['tier']}] {r['analyst']} {r['timestamp']}"
        lines.append(head)
        lines.append(f"   {r['subject'][:90]}")
        details = []
        if r["held_hits"]:
            details.append(f"HELD: {','.join(r['held_hits'])}")
        if r["thesis_hits"]:
            details.append("THESIS: " + ", ".join(
                f"{t}({'/'.join(kw[:2])})" for t, kw in r["thesis_hits"].items()
            ))
        if r["watchlist_hits"]:
            details.append(f"WL: {','.join(r['watchlist_hits'])}")
        if r["macro_themes"]:
            details.append(f"THEME: {','.join(r['macro_themes'])}")
        if details:
            lines.append("   " + " | ".join(details))
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        entries = json.load(sys.stdin)
    else:
        entries = [{"subject": "stdin", "body": sys.stdin.read(), "timestamp": ""}]
    ranked = rank_entries(entries)
    print(format_for_sprint(ranked, max_show=10))
