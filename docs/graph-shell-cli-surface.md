# Graph Shell CLI Surface

## Goal

The graph shell should be promptable from the CLI without turning into arbitrary generated UI.

The CLI therefore needs to:

1. accept natural-language shell prompts
2. compile them into a deterministic `ShellSpec`
3. open the explorer with that spec applied
4. let humans and agents iterate on the shell in a repeatable way

## Design principles

- promptable, but deterministic
- short commands for humans
- explicit subcommands for agents
- exportable/importable shell specs
- no hidden schema guessing required

## Primary command family

```bash
blockintql graph ...
```

This command family is for shaping the analyst shell itself, not for running investigation expansions.

## Human-first commands

### Launch a shell from a prompt

```bash
blockintql graph shell "Build a compact graph-first analyst workstation with floating controls and a wide evidence drawer"
```

Expected behavior:

- compile prompt into a `ShellSpec`
- open the explorer window
- load the shell with the compiled spec
- show the active prompt and matched rules in the explorer

### Launch a shell for a specific wallet

```bash
blockintql graph shell "Graph-first with a wide evidence drawer" --seed 0x873eb6ad683b224b669dc6b783e4b77ba06cf4a9
```

Expected behavior:

- same as above
- seed the explorer with the requested wallet

### Launch without opening the browser

```bash
blockintql graph shell "Table-first review surface with compact density" --no-open
```

Expected behavior:

- compile prompt
- print the compiled spec and shell session id
- do not open a window

## Iteration commands

### Refine the active shell

```bash
blockintql graph refine "Make the drawer wider and switch to table-first review mode"
```

Expected behavior:

- apply refinement to the current shell session
- recompile the shell spec
- update the explorer if it is open

### Refine a specific shell session

```bash
blockintql graph refine "Use executive tone with balanced graph and drawer space" --session shell_01
```

Expected behavior:

- target an existing shell session explicitly
- print the updated spec

### Print the current shell state

```bash
blockintql graph inspect
```

Expected behavior:

- show:
  - session id
  - active prompt
  - compiled `ShellSpec`
  - matched prompt rules
  - seed if present

## Agent-safe commands

Agents should not be forced to scrape prose. The CLI should expose deterministic outputs.

### Compile only

```bash
blockintql graph compile "Compact graph-first shell with floating controls" --json
```

Expected behavior:

- do not open a window
- return only structured JSON

Example output shape:

```json
{
  "prompt": "Compact graph-first shell with floating controls",
  "spec": {
    "tone": "analyst",
    "density": "compact",
    "chrome": "floating",
    "graphPriority": "canvas",
    "drawerMode": "right"
  },
  "matched_rules": [
    "compact density",
    "floating chrome",
    "graph-first canvas"
  ]
}
```

### Export the active shell spec

```bash
blockintql graph export-spec --json
```

Expected behavior:

- print the active `ShellSpec`
- optionally include session metadata

### Apply a spec directly

```bash
blockintql graph apply-spec ./shell-spec.json --open
```

Expected behavior:

- bypass prompt parsing
- load an already-approved deterministic shell spec

This matters for:

- agents
- automation
- reproducible demos
- open-source examples

## Recommended subcommands

The public CLI surface should support:

- `blockintql graph shell "<prompt>"`
- `blockintql graph refine "<prompt>"`
- `blockintql graph inspect`
- `blockintql graph compile "<prompt>" --json`
- `blockintql graph export-spec`
- `blockintql graph apply-spec <file>`

## Recommended flags

- `--seed <address>`
- `--open`
- `--no-open`
- `--session <id>`
- `--json`
- `--yaml`

## Explorer iteration model

The explorer should also expose the same prompt loop in-window:

1. user launches from CLI
2. explorer opens with prompt and compiled spec
3. user edits the prompt in `Prompt Studio`
4. shell recompiles in place
5. CLI and window stay in sync through the same deterministic contract

## What not to do

Do not support:

- arbitrary CSS generation
- arbitrary HTML generation
- model-written JSX at runtime
- freeform prompt injection into the shell renderer

The prompt layer should only modify the shell through validated spec fields.
