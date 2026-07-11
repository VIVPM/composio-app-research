"""
Doc-extraction layer — the web+LLM half of the research agent.

Composio settles auth/surface/buildability for the ~55 apps it ships (see
composio_lookup.py). This module fills what Composio can't: the one-line
description, self-serve vs gated (+ gate type), REST/GraphQL confirmation,
whether a first-party MCP exists, the main blocker, and an evidence URL — for
ALL 100 apps, including the ones Composio doesn't have.

It is LLM-pluggable. Default provider is Google Gemini (free self-serve tier)
with Google-Search grounding, so a reviewer needs only a GEMINI_API_KEY to
re-run the whole pipeline. Set LLM_PROVIDER=none to skip live calls and keep a
hand/Claude-authored data/doc_fields.json (how this repo's committed pass was
produced — see README "where a human was needed").

Run:  python agent/extract.py            # all 100
      python agent/extract.py 61 71 81   # only these app ids
Env:  GEMINI_API_KEY (if LLM_PROVIDER=gemini, the default)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-2.0-flash:generateContent")

# The exact contract we want back per app. Kept in the prompt so any provider
# returns the same shape.
SCHEMA_HINT = """Return ONLY a JSON object with these keys:
{
 "description": "<=15 word one-liner of what the app does",
 "auth_methods": ["OAuth2"|"API key"|"Basic"|"Token"|"Service account"|"Other", ...],
 "access": "self_serve" | "gated",
 "gate_type": "free" | "trial" | "paid" | "admin_approval" | "partner" | "contact_sales",
 "api_surface": {"type": "REST"|"GraphQL"|"gRPC"|"SDK"|"none",
                 "breadth": "narrow"|"medium"|"broad",
                 "notes": "<short>"},
 "existing_mcp": {"has": true|false, "url": "<url or empty>"},
 "buildability": "buildable_today" | "partial" | "blocked",
 "blocker": "<main blocker, or empty if buildable_today>",
 "evidence": ["<docs URL 1>", "<docs URL 2>"],
 "confidence": "high"|"med"|"low"
}
Rules: a developer can self_serve only if they can get working API credentials
themselves on a free or trial plan without sales/admin/partner approval. If the
API needs a paid plan, partner status, or contact-sales, it is gated — say so;
that is a correct finding, not a failure. Base every field on the app's real
developer docs and cite them in evidence."""


def prompt_for(app: dict) -> str:
    return (f"Research the app '{app['name']}' (hint: {app.get('hint','')}, "
            f"category: {app['category']}). Use web search to check its official "
            f"developer/API documentation.\n\n{SCHEMA_HINT}")


def call_gemini(prompt: str) -> dict:
    if not GEMINI_KEY:
        raise SystemExit("LLM_PROVIDER=gemini but no GEMINI_API_KEY in .env")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0},
    }
    r = requests.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body, timeout=90)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    m = re.search(r"\{.*\}", text, re.DOTALL)  # strip any markdown fences
    return json.loads(m.group(0)) if m else {"error": "unparseable", "raw": text}


def main(ids):
    apps = json.loads((DATA / "apps.json").read_text(encoding="utf-8"))["apps"]
    if ids:
        apps = [a for a in apps if a["id"] in ids]

    if PROVIDER == "none":
        print("LLM_PROVIDER=none -> keeping existing data/doc_fields.json (no live calls).")
        return

    out_path = DATA / "doc_fields.json"
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    for app in apps:
        try:
            fields = call_gemini(prompt_for(app)) if PROVIDER == "gemini" else {}
            fields["source"] = f"llm_web:{PROVIDER}"
            out[str(app["id"])] = fields
            print(f"[{app['id']:>3}] {app['name']:22} -> {fields.get('access','?')} "
                  f"/ {fields.get('buildability','?')} ({fields.get('confidence','?')})")
        except Exception as e:
            print(f"[{app['id']:>3}] {app['name']:22} -> ERROR {e}")
        time.sleep(1)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
