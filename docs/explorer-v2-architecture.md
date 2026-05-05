# Explorer V2 Architecture

## Why this exists

This is the open-source graph shell and UX foundation for BlockINTQL-style investigation surfaces.

It is intentionally focused on:

- analyst-first graph layout
- node selection
- right-side transaction drawer
- holdings and wallet summary
- graph expansion controls

It is intentionally not coupled to any proprietary runtime or private backend implementation.

## Frontend stack

- React
- Cytoscape.js
- Zustand
- TanStack Table
- Vite

## Product contract

The graph explorer should feel like:

1. graph stage on the left
2. agent timeline on the right
3. analyst drawer beneath that timeline
4. transaction evidence visible after node selection
5. expansions as additive graph actions, not prerequisites for basic wallet inspection

## Prompt-shaped shell contract

Users should be able to describe the workstation they want in natural language, but the shell must remain deterministic.

That means prompts should compile into a constrained `ShellSpec`, not arbitrary generated markup.

### Safe compilation model

- user prompt
- deterministic prompt compiler
- validated `ShellSpec`
- React components render from the spec

### `ShellSpec`

- `tone`
  - `analyst`
  - `executive`
  - `builder`
- `density`
  - `compact`
  - `comfortable`
- `chrome`
  - `floating`
  - `docked`
- `graphPriority`
  - `canvas`
  - `balanced`
  - `table`
- `drawerMode`
  - `right`
  - `wide`

### Why this matters

- makes the shell promptable without becoming arbitrary AI UI generation
- keeps the open-source app auditable
- preserves deterministic rendering consistent with the BlockINTQL paper approach

## State model

- `workspace`: id, title, goal, status
- `graph`: nodes, edges, graph state
- `selection`: selected node, selected edge, selected transaction row
- `drawer`: node summary, holdings, metrics, transactions
- `orchestrator`: ordered investigation steps with status, cost, and source
- `actions`: run expansion, sync artifacts, hydrate graph

## Suggested backend contract

### Graph payload

- `nodes`
- `edges`
- `graph_state`
- `artifact_count`

### Node drawer payload

- `address`
- `metrics`
- `holdings`
- `transactions`

### Orchestrator payload

- `steps`
  - `id`
  - `label`
  - `detail`
  - `status`
  - `credits`
  - `usd`
  - `source`

### Why the orchestrator matters

- makes the investigation feel actively built, not statically rendered
- shows users what the agent did, in what order, and at what cost
- gives the shell a true agentic runtime surface consistent with the "Replit for blockchain analytics" goal

## Open-source boundary

This app is safe to open source because it ships:

- UX shell
- graph interaction model
- mock/demo data
- frontend state structure

It does not ship:

- private investigation data
- private runtime orchestration
- private warehouse jobs
- secrets or provider credentials
