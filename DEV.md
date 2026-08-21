# Dev setup for BlockINTQL chat

## Quick start for testing the rich terminal UI + local server bypass

1. Activate the dev venv (or use the wrapper below):
   source /Users/block6iq/Documents/Playground/.venv-x402/bin/activate

2. (Optional but recommended) Start the local blockintql server with admin bypass:
   cd /Users/block6iq/blockintql
   python main.py

3. In another shell, test the rich chat (uses local server + admin key, 0 cost, full panels):
   export BLOCKINTQL_API_URL=http://127.0.0.1:8000
   export BLOCKINTQL_API_KEY=biq_sk_live_YOUR_DEV_KEY   # use the admin bypass value only on your local server with the matching middleware check
   blockintql chat "screen 0xc124ee65490ce130c0ffbf098710a2780c0adab9 for laundering risk"

**Easiest local testing (no key required at all):**
```bash
export BLOCKINTQL_API_URL=http://127.0.0.1:8000
export BLOCKINTQL_DEV_NO_AUTH=1     # disables API key requirement on the server until public release
```
Then just run `~/bin/blockintql` or `~/bin/blockintql verdict --address 0x...` etc. No need to export the long admin key every time. The server will automatically treat all requests as admin dev bypass (unlimited credits, full [GROUNDED] responses).

4. The graph web UI (explorer-v2: Cytoscape canvas, upload/paste seeds, PromptStudio for custom shells, live data) is now served automatically by the same local server:
   http://127.0.0.1:8000/explorer-react/
   The CLI auto-discovers it when BLOCKINTQL_API_URL is your local server, so:
   blockintql graph shell "Build a graph-first analyst workstation with floating controls and a right-side evidence drawer." --seed 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0 --open
   (or just run bare `blockintql graph` and type a prompt). No separate vite/http.server needed for the explorer.

## Making plain `blockintql` always use dev source (no PYTHONPATH every time)

A wrapper has been created at ~/bin/blockintql (see the bin/ in your home).

Make sure ~/bin is early in your PATH:
   export PATH=$HOME/bin:$PATH
   hash -r

Then just:
   blockintql chat ...

The wrapper forces PYTHONPATH to this source + calls the venv entrypoint.

## Notes
- The rich REPL (grounded panels, citations, 0-cost) is in the dev source.
- The local server has hardcoded bypass for the admin test key so you can test without any payments/credits/DB.
- To "update" to latest dev: cd here; git pull (or checkout the branch); the wrapper or activate will pick it up. After editing the local server (blockintql/main.py) — including the /explorer-react graph mount — restart the uvicorn process.
- When the admin bypass is active you will see a "[DEV SIM - local bypass, not production labels]" note. Sentinel will now correctly hit known OFAC addresses from the real list for test cases.
- For production-like: unset the API_URL (defaults to https://blockintql.com) once your changes are deployed.


## Setting your API key for a shell session (so smoke tests and hosted paths work)

For a single shell session (e.g. before running smoke):

```bash
export BLOCKINTQL_API_KEY=biq_sk_live_YOUR_REAL_OR_DEV_KEY
```

For local dev + smoke tests (no credits, local deterministic, graph shell):

```bash
export BLOCKINTQL_API_URL=http://127.0.0.1:8000
export BLOCKINTQL_DEV_NO_AUTH=1
```

Then:

```bash
~/bin/blockintql deterministic eval
~/bin/blockintql graph shell "..." --seed 0x... --json
bash scripts/v1_smoke.sh 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0
```

The wrapper and code will automatically prefer the pure local path for chat, grounded, deterministic adjudicate, evidence bundles etc. A real key in the env or in ~/.blockintql/config.json (from `blockintql auth`) is used for any paths that still go over the network.

Run `hash -r` after editing PATH or the wrapper.
