"""
Verification — how we know the findings are trustworthy, and how accuracy moved
from the first pass to the final one.

Two loops:

  Loop 1 (automatic, zero web calls): auth cross-check.
    For every app Composio actually ships, the first-pass doc layer produced an
    INDEPENDENT auth guess (from the LLM/knowledge pass, never shown Composio's
    answer). We score that guess against Composio's catalog ground truth. This
    is a free, objective accuracy signal on the single most important field.

  Loop 2 (browser/web, on a stratified sample): the doc-only fields
    (self-serve vs gated, first-party MCP) can't be checked against Composio, so
    a human/agent opens the real docs for a sample and records hits/misses. That
    sample lives in data/verification_sample.json (filled by the reviewer or by
    Claude Code's browser/web pass); this script folds it into the final score.

Run:  python agent/verify.py   ->  data/verification.json (+ printed report)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CATS = [
    "CRM and Sales", "Support and Helpdesk", "Communications and Messaging",
    "Marketing, Ads, Email and Social", "Ecommerce", "Data, SEO and Scraping",
    "Developer, Infra and Data platforms", "Productivity and Project Management",
    "Finance and Fintech", "AI, Research and Media-native",
]


def auth_crosscheck(results, matches, docs):
    """Score first-pass doc auth guess vs Composio ground truth on matched apps."""
    rows, exact, overlap = [], 0, 0
    for r in results:
        cm = matches.get(r["id"], {})
        if not cm.get("slug") or not cm.get("auth_methods"):
            continue
        truth = set(cm["auth_methods"])
        guess = set((docs.get(str(r["id"])) or {}).get("auth_methods", []))
        is_exact = guess == truth
        is_overlap = bool(guess & truth)
        exact += is_exact
        overlap += is_overlap
        rows.append({"id": r["id"], "name": r["name"], "guess": sorted(guess),
                     "truth": sorted(truth), "exact": is_exact, "overlap": is_overlap})
    n = len(rows)
    return {
        "n": n,
        "exact_match_pct": round(100 * exact / n) if n else 0,
        "overlap_pct": round(100 * overlap / n) if n else 0,
        "misses": [x for x in rows if not x["overlap"]],
        "rows": rows,
    }


def pick_sample(results, per_cat=2):
    """Deterministic stratified sample: first `per_cat` apps per category by id."""
    sample = []
    for c in CATS:
        got = [r["id"] for r in sorted(results, key=lambda x: x["id"]) if r["category"] == c]
        sample += got[:per_cat]
    return sample


def main():
    results = json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    matches = {m["id"]: m for m in json.loads((DATA / "composio_matches.json").read_text(encoding="utf-8"))}
    docs = json.loads((DATA / "doc_fields.json").read_text(encoding="utf-8"))

    loop1 = auth_crosscheck(results, matches, docs)

    sample_ids = pick_sample(results)
    sample_path = DATA / "verification_sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.exists() else {}

    # Loop 2 scoring from the hand/browser-checked sample (if present)
    checked = [sample[str(i)] for i in sample_ids if str(i) in sample]
    fields = ["auth_methods", "access", "existing_mcp"]
    loop2 = {"sample_size": len(sample_ids), "checked": len(checked), "by_field": {}}
    for f in fields:
        judged = [c for c in checked if f in c.get("verdict", {})]
        hits = sum(1 for c in judged if c["verdict"][f] == "correct")
        loop2["by_field"][f] = {"checked": len(judged), "correct": hits,
                                "pct": round(100 * hits / len(judged)) if judged else None}
    allj = [(f, c) for c in checked for f in fields if f in c.get("verdict", {})]
    hits = sum(1 for f, c in allj if c["verdict"][f] == "correct")
    loop2["overall_first_pass_pct"] = round(100 * hits / len(allj)) if allj else None

    out = {
        "loop1_auth_crosscheck": loop1,
        "loop2_sample": loop2,
        "sample_ids": sample_ids,
        "notes": "Loop1 = independent first-pass auth guess vs Composio ground truth. "
                 "Loop2 = docs opened by hand/browser for the sample; misses corrected in results.json.",
    }
    (DATA / "verification.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("=== Loop 1: auth cross-check vs Composio ground truth ===")
    print(f"  matched apps scored: {loop1['n']}")
    print(f"  exact set match:     {loop1['exact_match_pct']}%")
    print(f"  overlap (>=1 method):{loop1['overlap_pct']}%")
    if loop1["misses"]:
        print("  first-pass MISSES (no shared method):")
        for m in loop1["misses"]:
            print(f"    {m['name']:18} guess={m['guess']} truth={m['truth']}")
    print(f"\n=== Loop 2: stratified sample ({len(sample_ids)} apps, ids {sample_ids}) ===")
    print(f"  checked: {loop2['checked']}/{loop2['sample_size']}  "
          f"(fill data/verification_sample.json to score)")
    if loop2["overall_first_pass_pct"] is not None:
        print(f"  first-pass accuracy on sample: {loop2['overall_first_pass_pct']}%")


if __name__ == "__main__":
    main()
