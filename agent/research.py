"""
Orchestrator — merges the two research layers into data/results.json.

  composio_matches.json  (ground truth: auth, tool count, support)   <- composio_lookup.py
  doc_fields.json        (web+LLM: description, gated?, MCP, blocker) <- extract.py

Merge policy: Composio is authoritative for auth method and API-surface breadth
whenever it ships the toolkit (objective catalog data); the doc layer supplies
everything Composio can't, and is the sole source for the ~45 apps Composio
doesn't have. Every record keeps provenance (which layer set auth) and a
confidence so the verification pass and the HTML can be honest about it.

Run:  python agent/research.py   (after composio_lookup.py and doc_fields.json exist)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def breadth_from_count(n):
    if not n:
        return None
    return "broad" if n >= 100 else "medium" if n >= 30 else "narrow"


def merge():
    apps = json.loads((DATA / "apps.json").read_text(encoding="utf-8"))["apps"]
    matches = {m["id"]: m for m in json.loads((DATA / "composio_matches.json").read_text(encoding="utf-8"))}
    docs = json.loads((DATA / "doc_fields.json").read_text(encoding="utf-8"))

    results = []
    for app in apps:
        cm = matches.get(app["id"], {})
        doc = docs.get(str(app["id"]), {})
        supported = bool(cm.get("slug"))
        tools = cm.get("tools_count")

        # auth: Composio wins when present, else doc layer
        if supported and cm.get("auth_methods"):
            auth, auth_source = cm["auth_methods"], "composio_catalog"
        else:
            auth, auth_source = doc.get("auth_methods", []), doc.get("source", "llm_web")

        # api surface: type/notes from doc, breadth from Composio count when we have it
        doc_surface = doc.get("api_surface", {}) or {}
        breadth = breadth_from_count(tools) or doc_surface.get("breadth")
        notes = doc_surface.get("notes", "")
        if supported and tools:
            notes = (notes + f" · {tools} Composio tools").strip(" ·")

        evidence = []
        if cm.get("evidence"):
            evidence.append(cm["evidence"])
        evidence += [e for e in doc.get("evidence", []) if e]
        evidence = list(dict.fromkeys(evidence))  # dedup, keep order

        results.append({
            "id": app["id"],
            "name": app["name"],
            "category": app["category"],
            "hint": app.get("hint", ""),
            "description": doc.get("description") or cm.get("composio_description") or "",
            "auth_methods": auth,
            "auth_source": auth_source,
            "access": doc.get("access"),
            "gate_type": doc.get("gate_type"),
            "api_surface": {"type": doc_surface.get("type"), "breadth": breadth, "notes": notes},
            "existing_mcp": doc.get("existing_mcp", {"has": None, "url": ""}),
            "composio_supported": supported,
            "composio_slug": cm.get("slug"),
            "composio_tools_count": tools,
            "buildability": doc.get("buildability"),
            "blocker": doc.get("blocker", ""),
            "evidence": evidence,
            "confidence": doc.get("confidence", "low"),
            "verified": doc.get("verified", False),
        })

    (DATA / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # quick sanity summary
    filled = [r for r in results if r["access"] and r["auth_methods"]]
    print(f"merged {len(results)} apps -> results.json  ({len(filled)} fully filled)")
    miss = [r["name"] for r in results if not r["access"] or not r["auth_methods"]]
    if miss:
        print(f"MISSING access/auth ({len(miss)}): {', '.join(miss)}")


if __name__ == "__main__":
    merge()
