# Open-Source Explorer V2

The public repo now includes an open-source graph explorer shell in:

`apps/explorer-v2`

## What it is

A React + Cytoscape.js analyst graph foundation with:

- graph canvas
- node selection
- right-side node transaction drawer
- holdings section
- transaction table
- node expansion

## What it is not

- a complete hosted investigation product
- a private runtime
- a warehouse execution engine

## Why ship it publicly

So other builders can:

- study the interaction model
- build their own graph explorer
- connect it to their own blockchain datasets
- extend the shell without needing the hosted BlockINTQL stack

## Next recommended public steps

1. wire the app to a public demo JSON contract
2. add edge highlighting and row selection
3. add prompt-to-shell compilation using the constrained `ShellSpec`
4. add graph expansion from selected node

## Prompting the shell

The open-source explorer should support prompts like:

- `Build a compact graph-first shell with floating controls`
- `Make this a table-first review surface with a wide evidence drawer`
- `Use an executive briefing tone with balanced graph and drawer space`

Those prompts should not generate arbitrary UI code.

Instead, they should map into a deterministic shell spec that controls:

- visual tone
- layout density
- toolbar behavior
- graph-vs-drawer emphasis
- drawer width

See also:

- [Graph Shell CLI Surface](graph-shell-cli-surface.md)
