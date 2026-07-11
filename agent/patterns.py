"""
Pattern analysis — turns results.json into the headline clusters the case study
leads with. Insight over raw rows: which auth dominates, which categories are
self-serve vs gated, the most common blocker, and where the easy wins are.

Run:  python agent/patterns.py   ->  data/patterns.json (+ printed summary)
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def pct(n, d):
    return round(100 * n / d) if d else 0


def classify_blocker(r):
    """Bucket the free-text blocker into a coarse, countable reason."""
    if r["buildability"] == "buildable_today":
        return None
    b = (r["blocker"] or "").lower()
    g = r.get("gate_type")
    if "no public" in b or "no clearly" in b or r["buildability"] == "blocked" and "license" not in b:
        if "no public" in b or "no clearly" in b:
            return "no public API"
    if g == "partner" or "partner" in b or "registration" in b or "app review" in b or "approval" in b:
        return "approval / partner gate"
    if g == "contact_sales" or "enterprise" in b or "license" in b or "sales" in b:
        return "enterprise / contact-sales"
    if g == "paid" or "customer" in b or "account" in b or "paid" in b:
        return "must be a paying customer"
    return "other"


def main():
    apps = json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    n = len(apps)

    # --- auth distribution (an app can list several) ---
    auth = Counter()
    for r in apps:
        for a in r["auth_methods"]:
            auth[a] += 1
    apps_with_oauth = sum(1 for r in apps if "OAuth2" in r["auth_methods"])
    apps_with_apikey = sum(1 for r in apps if "API key" in r["auth_methods"])

    # --- access overall + by category ---
    access = Counter(r["access"] for r in apps)
    by_cat = defaultdict(lambda: Counter())
    for r in apps:
        by_cat[r["category"]][r["access"]] += 1
    cat_access = {c: {"self_serve": v["self_serve"], "gated": v["gated"], "total": sum(v.values())}
                  for c, v in by_cat.items()}

    # --- buildability, gates, blockers ---
    build = Counter(r["buildability"] for r in apps)
    gates = Counter(r["gate_type"] for r in apps if r["access"] == "gated")
    blockers = Counter(b for b in (classify_blocker(r) for r in apps) if b)

    # --- composio coverage, MCP, breadth ---
    composio = sum(1 for r in apps if r["composio_supported"])
    mcp = sum(1 for r in apps if (r["existing_mcp"] or {}).get("has"))
    breadth = Counter(r["api_surface"]["breadth"] for r in apps)

    # --- easy wins vs outreach-needed ---
    def easy(r):
        return (r["access"] == "self_serve" and r["buildability"] == "buildable_today"
                and (r["api_surface"]["type"] or "").lower() not in ("none", ""))
    easy_wins = [r["name"] for r in apps if easy(r)]
    outreach = [r["name"] for r in apps
                if r["buildability"] == "blocked"
                or r.get("gate_type") in ("partner", "contact_sales", "admin_approval")]

    patterns = {
        "n": n,
        "headline": {
            "oauth2_or_apikey_share": pct(sum(1 for r in apps if {"OAuth2", "API key"} & set(r["auth_methods"])), n),
            "oauth2_share": pct(apps_with_oauth, n),
            "apikey_share": pct(apps_with_apikey, n),
            "self_serve_share": pct(access["self_serve"], n),
            "gated_share": pct(access["gated"], n),
            "buildable_today_share": pct(build["buildable_today"], n),
            "composio_supported": composio,
            "existing_mcp": mcp,
        },
        "auth_distribution": dict(auth.most_common()),
        "access": dict(access),
        "access_by_category": cat_access,
        "buildability": dict(build),
        "gate_types": dict(gates.most_common()),
        "top_blockers": dict(blockers.most_common()),
        "api_breadth": dict(breadth),
        "easy_wins": {"count": len(easy_wins), "apps": easy_wins},
        "outreach_needed": {"count": len(outreach), "apps": outreach},
    }
    (DATA / "patterns.json").write_text(json.dumps(patterns, indent=2), encoding="utf-8")

    h = patterns["headline"]
    print(f"=== {n} apps ===")
    print(f"OAuth2 or API key: {h['oauth2_or_apikey_share']}%  (OAuth2 {h['oauth2_share']}%, API key {h['apikey_share']}%)")
    print(f"Self-serve: {h['self_serve_share']}%   Gated: {h['gated_share']}%   Buildable today: {h['buildable_today_share']}%")
    print(f"Composio already ships: {composio}/{n}   First-party MCP: {mcp}/{n}")
    print(f"\nGate types: {patterns['gate_types']}")
    print(f"Top blockers: {patterns['top_blockers']}")
    print(f"\nMost-gated categories:")
    for c, v in sorted(cat_access.items(), key=lambda kv: kv[1]['gated'], reverse=True)[:4]:
        print(f"  {c:36} gated {v['gated']}/{v['total']}")
    print(f"\nEasy wins: {len(easy_wins)} | Outreach-needed: {len(outreach)}")


if __name__ == "__main__":
    main()
