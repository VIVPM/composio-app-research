"""
Proof app — a tiny Composio-powered GitHub agent (the "it runs" evidence).

GitHub was the top-right easy win in the research (self-serve OAuth/PAT,
REST+GraphQL, 871 Composio tools), so the runnable trigger acts on GitHub
*through Composio* — the same platform the research agent used.

Flow: ensure the user's GitHub is connected via Composio (authorize once in the
browser), then execute GITHUB_CREATE_AN_ISSUE and print the new issue's URL.

Usage:
  export COMPOSIO_API_KEY=...                       # same key the research agent uses
  python proof/github_agent.py "Ship the case study" --repo you/yourrepo
  python proof/github_agent.py "Bug: x" --repo you/repo --body "steps..." --user alice

  python proof/github_agent.py "t" --repo you/repo --dry-run   # parse only, no API/network
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def split_repo(repo: str):
    """'owner/name' -> ('owner', 'name'). Raises on anything else."""
    parts = repo.strip().strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"--repo must be 'owner/name', got {repo!r}")
    return parts[0], parts[1]


def _github_auth_config_id(composio) -> str:
    """Find the GitHub auth config, creating a Composio-managed one if none exists."""
    for a in getattr(composio.auth_configs.list(), "items", []):
        tk = getattr(a, "toolkit", None)
        slug = tk.get("slug") if isinstance(tk, dict) else getattr(tk, "slug", tk)
        if str(slug).lower() == "github":
            return a.id
    try:  # no config yet -> create a Composio-managed OAuth one
        return composio.auth_configs.create(
            toolkit="github", options={"type": "use_composio_managed_auth"}).id
    except Exception as e:
        raise SystemExit(
            "No GitHub auth config found and auto-create failed "
            f"({e}). Create one at https://platform.composio.dev (toolkit: GitHub).")


def ensure_github(composio, user_id: str):
    """Ensure an ACTIVE GitHub connection, running the browser auth flow if needed."""
    existing = composio.connected_accounts.list(
        user_ids=[user_id], toolkit_slugs=["github"], statuses=["ACTIVE"])
    if getattr(existing, "items", None):
        return
    # toolkits.authorize hits a retired endpoint for Composio-managed OAuth;
    # the current flow is connected_accounts.link(user_id, auth_config_id).
    req = composio.connected_accounts.link(
        user_id=user_id, auth_config_id=_github_auth_config_id(composio))
    print(f"\nAuthorize GitHub for user '{user_id}' — open this URL:\n  {req.redirect_url}\n")
    if hasattr(req, "wait_for_connection"):
        req.wait_for_connection()
    else:
        composio.connected_accounts.wait_for_connection(req.id)
    print("GitHub connected.\n")


def main():
    ap = argparse.ArgumentParser(description="Create a GitHub issue via Composio.")
    ap.add_argument("title", help="issue title")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--body", default="Filed by the Composio research proof agent.")
    ap.add_argument("--user", default="default", help="Composio user id")
    ap.add_argument("--dry-run", action="store_true", help="parse args only; no network")
    args = ap.parse_args()

    owner, name = split_repo(args.repo)
    if args.dry_run:
        print(f"[dry-run] would create issue '{args.title}' in {owner}/{name}")
        return

    if not os.getenv("COMPOSIO_API_KEY"):
        sys.exit("Set COMPOSIO_API_KEY (env or .env).")

    from composio import Composio
    composio = Composio()
    ensure_github(composio, args.user)

    res = composio.tools.execute(
        "GITHUB_CREATE_AN_ISSUE",
        arguments={"owner": owner, "repo": name, "title": args.title, "body": args.body},
        user_id=args.user,
    )
    data = getattr(res, "data", res) or {}
    if getattr(res, "successful", True) is False:
        sys.exit(f"Composio error: {getattr(res, 'error', 'unknown')}")
    url = (data.get("html_url") if isinstance(data, dict) else None) or "(created — see repo)"
    print(f"Created issue: {url}")


def _selfcheck():
    assert split_repo("octocat/Hello-World") == ("octocat", "Hello-World")
    for bad in ("noslash", "a/b/c", "/x", "x/", ""):
        try:
            split_repo(bad); raise AssertionError(f"expected failure for {bad!r}")
        except ValueError:
            pass
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
