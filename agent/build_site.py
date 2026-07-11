"""
Build the self-contained case study: inject the live data JSON into
site/index.html so the page always matches data/*.json (no server, no fetch —
open it as a file or on GitHub Pages).

Run:  python agent/build_site.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "docs" / "index.html"

REPO = "https://github.com/VIVPM/composio-app-research"  # updated at deploy time


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    payload = {
        "results": load("results.json", []),
        "patterns": load("patterns.json", {}),
        "verification": load("verification.json", {}),
        "sample": load("verification_sample.json", {}),
        "meta": {"repo": REPO},
    }
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    # escape </script> so the JSON can't break out of the tag
    blob = blob.replace("</", "<\\/")

    html = SITE.read_text(encoding="utf-8")
    new = re.sub(
        r'(<script id="appdata" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + blob + m.group(2),
        html, count=1, flags=re.DOTALL,
    )
    SITE.write_text(new, encoding="utf-8")
    kb = len(new.encode("utf-8")) / 1024
    print(f"built {SITE.relative_to(ROOT).as_posix()}  ({kb:.0f} KB, {len(payload['results'])} apps embedded)")


if __name__ == "__main__":
    main()
