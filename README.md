# Composio App Research — 100 apps, one agent, verified

An agent researches 100 apps across 10 categories — auth method, self-serve vs
gated, API surface, existing MCP, and whether each could be an agent toolkit
today — then **verifies its own accuracy** and presents everything as one
self-explanatory page.

- **Live case study:** _deployed to GitHub Pages_ → `https://vivpm.github.io/composio-app-research/`
- **What it's for:** the AI Product Ops take-home — insight over a raw table, an agent that does the research, and proof the findings are trustworthy.

## The headline (computed from `data/results.json`)

| | |
|---|---|
| **97%** use OAuth2 or an API key | 62% OAuth2, 58% API key — build two flows, cover almost everything |
| **74%** are self-serve | a developer gets credentials on a free/trial plan |
| **77%** are buildable as a toolkit today | 20 partial (need an approval/review step), 3 blocked (no public API) |
| **55/100** already ship in Composio | ground-truth auth + tool counts come straight from its catalog |
| **30/100** have a first-party MCP | up from 28 after verification caught two |
| Most-gated categories | **Finance** and **AI/Research** (5/10 each) — payments, capital-markets data, closed AI |

## How the agent works

Two layers, cheapest-source-first:

1. **Composio catalog (ground truth)** — `agent/composio_lookup.py` pulls all 1,047
   toolkits from the Composio v3 REST API and matches each app. For the 55 it ships,
   auth scheme, tool count and buildability come from the catalog, not a guess.
2. **Web + LLM (doc layer)** — `agent/extract.py` fills description, self-serve vs
   gated, REST/GraphQL, first-party MCP, blocker and evidence for all 100, and is the
   sole source for the 45 Composio doesn't have. LLM is pluggable (defaults to a free
   Gemini tier); this repo's committed pass was produced with Claude Code driving the
   web research, which is why `data/doc_fields.json` is checked in.

`agent/research.py` merges them into `data/results.json` (Composio wins on auth/breadth
where present; every field keeps its `source` + `confidence`).

## Verification (accuracy is the point)

- **Loop 1 — auth cross-check** (`agent/verify.py`, objective, zero web calls): the doc
  layer's independent auth guess scored against Composio ground truth on 55 apps →
  **96% overlap**, 62% exact-set (the gap is over-listing methods, not wrong ones); 2
  near-misses (Telegram, Vercel: "token" vs "API key").
- **Loop 2 — browser/web sample** (`data/verification_sample.json`): live docs opened by
  hand for a 20-app stratified sample → **96% first pass → 100%** after correcting 2
  missed first-party MCPs (Google Ads, SE Ranking), lifting the MCP count 28 → 30.
- **Honest limits:** the sample skews to marquee apps; `existing_mcp` is the least
  reliable field; one doc (Otter.ai) returned HTTP 403 and is held at first pass.

## Run it

```bash
pip install requests python-dotenv composio          # Python 3.12
echo "COMPOSIO_API_KEY=your_key" > .env               # from platform.composio.dev
# optional, to re-run the web+LLM layer live:  echo "GEMINI_API_KEY=..." >> .env

python agent/composio_lookup.py     # 1. catalog -> data/composio_catalog.json, matches
python agent/extract.py             # 2. web+LLM doc layer -> data/doc_fields.json
                                    #    (LLM_PROVIDER=none keeps the committed pass)
python agent/research.py            # 3. merge -> data/results.json
python agent/patterns.py            # 4. clusters -> data/patterns.json
python agent/verify.py              # 5. accuracy loops -> data/verification.json
python agent/build_site.py          # 6. inject data -> docs/index.html
```

Open `docs/index.html` (or serve `docs/` and browse). It's fully self-contained —
the data is embedded, no server or network needed to read it.

## Proof app — a working Composio agent

```bash
python proof/github_agent.py "Ship the case study" --repo you/yourrepo
# authorizes GitHub once via Composio, creates the issue, prints its URL
python proof/github_agent.py --selfcheck        # offline self-test
```

## Layout

```
agent/    composio_lookup · extract · research · patterns · verify · build_site
data/     apps.json (the 100) · composio_catalog · composio_matches · doc_fields
          · results.json · patterns.json · verification.json · verification_sample.json
proof/    github_agent.py     # runnable Composio GitHub agent
docs/     index.html          # the single self-contained deliverable (served by GitHub Pages)
```

## Notes & honesty

- No paid accounts were used. Where an app is gated behind payment/partnership,
  "gated" with evidence **is** the finding — not a failure.
- Composio's fuzzy matcher produced 4 false positives (Zoho Cliq→zoho, Squarespace→square,
  Plaid→_placid_, SF Commerce Cloud→salesforce); a human rejected them (see `REJECT` in
  `composio_lookup.py`).
- Everything on the page is computed from the JSON in `data/` — regenerate and rebuild
  to update.
