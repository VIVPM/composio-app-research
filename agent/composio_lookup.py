"""
Composio catalog layer — the ground-truth source for the research agent.

Fetches the full Composio toolkit catalog (v3 REST API) once, caches it, then
matches each of the 100 apps to a toolkit. For matched apps this settles, with
evidence, the fields that are otherwise guesswork:
  - auth method(s)      <- toolkit.auth_schemes
  - API-surface breadth <- toolkit.meta.tools_count
  - Composio support    <- match exists
  - buildable today     <- Composio already ships the toolkit

Unmatched apps fall through to the web+LLM layer (extract.py).

Run:  python agent/composio_lookup.py
Needs: COMPOSIO_API_KEY in .env  (see README)
"""
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("COMPOSIO_API_KEY")
BASE = "https://backend.composio.dev/api/v3"

# Composio auth_scheme mode -> assignment's auth vocabulary
AUTH_MAP = {
    "OAUTH2": "OAuth2",
    "OAUTH1": "OAuth1",
    "S2S_OAUTH2": "OAuth2",
    "DCR_OAUTH": "OAuth2",
    "API_KEY": "API key",
    "BEARER_TOKEN": "Token",
    "BASIC": "Basic",
    "BASIC_WITH_JWT": "Basic",
    "GOOGLE_SERVICE_ACCOUNT": "Service account",
    "NO_AUTH": "None",
    "BILLCOM_AUTH": "Other",
    "CALCOM_AUTH": "Other",
}

# False positives the fuzzy matcher produced that a human rejected on review:
# each is a distinct product from the toolkit it fuzzily matched, and none has a
# genuine toolkit in the catalog -> forced unmatched, sent to the web+LLM layer.
REJECT = {
    "Zoho Cliq",                  # matched "zoho" (CRM) — Cliq is a separate messaging app
    "Salesforce Commerce Cloud",  # matched "salesforce" (CRM) — different product/API
    "Squarespace",                # matched "square" (payments) — unrelated company
    "Plaid",                      # fuzzy-matched "placid" (image gen) — unrelated
}

# Hand aliases for names that don't normalize cleanly to a slug.
# (kept small on purpose — the fuzzy matcher handles the rest, and every
#  match is written out for human review.)
ALIASES = {
    "Monday.com": "monday",
    "Zoho CRM": "zoho",
    "Zoho Cliq": "zoho_cliq",
    "Google Ads": "google_ads",
    "Meta Ads": "metaads",
    "WhatsApp Business": "whatsapp",
    "Threads (Meta)": "threads",
    "Lark (Larksuite)": "lark",
    "Magento (Adobe Commerce)": "magento",
    "Help Scout": "helpscout",
    "MongoDB Atlas": "mongodb",
    "Otter AI": "otter",
    "systeme.io": "systeme",
    "Amazon Selling Partner": "amazon",
    "Salesforce Commerce Cloud": "salesforce_commerce",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fetch_catalog() -> dict:
    """Fetch every toolkit, cache to data/composio_catalog.json, return {slug: toolkit}."""
    cache = DATA / "composio_catalog.json"
    if cache.exists():
        print(f"[cache] using {cache.name}")
        return json.loads(cache.read_text(encoding="utf-8"))

    if not API_KEY:
        sys.exit("No COMPOSIO_API_KEY in .env")

    headers = {"x-api-key": API_KEY}
    out, cursor, pages = {}, None, 0
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{BASE}/toolkits", headers=headers, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        for tk in body.get("items", []):
            out[tk["slug"]] = tk
        pages += 1
        cursor = body.get("next_cursor")
        print(f"[catalog] page {pages} -> {len(out)} toolkits (total_items={body.get('total_items')})")
        if not cursor:
            break
        time.sleep(0.2)

    cache.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[catalog] cached {len(out)} toolkits -> {cache.name}")
    return out


def match_app(app: dict, catalog: dict, index: dict):
    """Return (slug, confidence, method) or (None, 0, 'none')."""
    name = app["name"]

    # 0) human-rejected false positives -> force unmatched
    if name in REJECT:
        return None, 0.0, "rejected"

    # 1) explicit alias
    alias = ALIASES.get(name)
    if alias and alias in catalog:
        return alias, 1.0, "alias"

    n = norm(name)
    # 2) exact normalized match against slug or toolkit name
    if n in index:
        return index[n], 1.0, "exact"

    # 3) substring either direction (guarded by length to avoid junk hits)
    best = None
    for key, slug in index.items():
        if len(n) >= 4 and (n == key or (len(key) >= 4 and (n in key or key in n))):
            ratio = SequenceMatcher(None, n, key).ratio()
            if best is None or ratio > best[1]:
                best = (slug, ratio)
    if best and best[1] >= 0.6:
        return best[0], round(best[1], 2), "substring"

    # 4) fuzzy fallback
    best = None
    for key, slug in index.items():
        ratio = SequenceMatcher(None, n, key).ratio()
        if best is None or ratio > best[1]:
            best = (slug, ratio)
    if best and best[1] >= 0.82:
        return best[0], round(best[1], 2), "fuzzy"

    return None, 0.0, "none"


def toolkit_fields(tk: dict) -> dict:
    schemes = tk.get("auth_schemes") or []
    meta = tk.get("meta") or {}
    mapped = [AUTH_MAP.get(s, str(s).title()) for s in schemes]
    auth = sorted({m for m in mapped if m}) or (["None"] if tk.get("no_auth") else [])
    return {
        "auth_methods": auth,
        "auth_schemes_raw": schemes,
        "tools_count": meta.get("tools_count"),
        "triggers_count": meta.get("triggers_count"),
        "categories": [c.get("name") for c in meta.get("categories", [])],
        "composio_description": meta.get("description"),
        "app_url": meta.get("app_url"),
    }


def main():
    apps = json.loads((DATA / "apps.json").read_text(encoding="utf-8"))["apps"]
    catalog = fetch_catalog()

    # normalized index: normalized(slug) and normalized(name) -> slug
    index = {}
    for slug, tk in catalog.items():
        index.setdefault(norm(slug), slug)
        index.setdefault(norm(tk.get("name", "")), slug)

    matches = []
    for app in apps:
        slug, conf, method = match_app(app, catalog, index)
        rec = {"id": app["id"], "name": app["name"], "category": app["category"],
               "slug": slug, "match_confidence": conf, "match_method": method}
        if slug:
            tk = catalog[slug]
            rec["toolkit_name"] = tk.get("name")
            rec.update(toolkit_fields(tk))
            rec["evidence"] = f"https://composio.dev/toolkit/{slug}"
        matches.append(rec)

    (DATA / "composio_matches.json").write_text(json.dumps(matches, indent=2), encoding="utf-8")

    matched = [m for m in matches if m["slug"]]
    print(f"\n=== matched {len(matched)}/{len(apps)} apps to Composio toolkits ===")
    print(f"{'id':>3} {'app':22} {'slug':22} {'conf':>4} {'method':9} {'auth':22} tools")
    for m in matches:
        auth = ",".join(m.get("auth_methods", [])) if m["slug"] else "-"
        print(f"{m['id']:>3} {m['name'][:22]:22} {str(m['slug'])[:22]:22} "
              f"{m['match_confidence']:>4} {m['match_method']:9} {auth[:22]:22} {m.get('tools_count','')}")

    # flag low-confidence matches for human review
    fuzzy = [m for m in matched if m["match_method"] in ("fuzzy", "substring")]
    if fuzzy:
        print(f"\n!! {len(fuzzy)} low-confidence matches to REVIEW BY HAND:")
        for m in fuzzy:
            print(f"   {m['name']}  ->  {m['slug']} ({m['match_method']} {m['match_confidence']})")


if __name__ == "__main__":
    main()
