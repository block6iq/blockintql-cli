import { defaultShellSpec, type ShellSpec } from "./shellSpec";

type CompiledPrompt = {
  spec: ShellSpec;
  matchedRules: string[];
};

function hasAny(input: string, phrases: string[]) {
  return phrases.some((phrase) => input.includes(phrase));
}

export function compileShellPrompt(prompt: string): CompiledPrompt {
  const normalized = prompt.trim().toLowerCase();
  const spec: ShellSpec = { ...defaultShellSpec };
  const matchedRules: string[] = [];

  if (!normalized) {
    return { spec, matchedRules };
  }

  if (hasAny(normalized, ["executive", "briefing", "presentation", "summary-first"])) {
    spec.tone = "executive";
    spec.graphPriority = "balanced";
    matchedRules.push("executive tone");
  }

  if (hasAny(normalized, ["for an investigator", "for investigators", "for investigations", "analyst workflow", "casework"])) {
    spec.tone = "analyst";
    matchedRules.push("investigator tone");
  }

  if (hasAny(normalized, ["perfect blockchain explorer", "perfect investigator graph", "blockchain analytics workstation", "serious analyst graph"])) {
    spec.tone = "analyst";
    spec.graphPriority = "canvas";
    spec.drawerMode = "wide";
    spec.investigationMode = "moneyflow";
    matchedRules.push("analyst workstation");
  }

  if (hasAny(normalized, ["builder", "workspace", "developer", "tooling"])) {
    spec.tone = "builder";
    spec.chrome = "docked";
    matchedRules.push("builder tone");
  }

  if (hasAny(normalized, ["compact", "dense", "more rows", "fit more"])) {
    spec.density = "compact";
    matchedRules.push("compact density");
  }

  if (hasAny(normalized, ["comfortable", "spacious", "bigger panels"])) {
    spec.density = "comfortable";
    matchedRules.push("comfortable density");
  }

  if (hasAny(normalized, ["floating controls", "floating chrome", "minimal chrome"])) {
    spec.chrome = "floating";
    matchedRules.push("floating chrome");
  }

  if (hasAny(normalized, ["docked controls", "toolbar", "control rail"])) {
    spec.chrome = "docked";
    matchedRules.push("docked chrome");
  }

  if (hasAny(normalized, ["graph first", "full canvas", "graph dominant", "canvas first"])) {
    spec.graphPriority = "canvas";
    matchedRules.push("graph-first canvas");
  }

  if (hasAny(normalized, ["follow the money", "money flow", "trace funds", "trace counterparties", "map relationships", "see counterparties"])) {
    spec.graphPriority = "canvas";
    spec.drawerMode = "wide";
    spec.density = "compact";
    spec.palette = "caseboard";
    spec.investigationMode = "moneyflow";
    matchedRules.push("money-flow workspace");
  }

  if (hasAny(normalized, ["table first", "transactions first", "ledger first"])) {
    spec.graphPriority = "table";
    spec.drawerMode = "wide";
    matchedRules.push("table-first investigation");
  }

  if (hasAny(normalized, ["review lots of transactions", "triage wallets fast", "scan many transfers", "evidence first", "show me the table"])) {
    spec.graphPriority = "table";
    spec.density = "compact";
    spec.drawerMode = "wide";
    spec.chrome = "docked";
    spec.investigationMode = "triage";
    matchedRules.push("evidence-first triage");
  }

  if (hasAny(normalized, ["case board", "case file", "investigation board", "war room"])) {
    spec.tone = "executive";
    spec.density = "compact";
    spec.chrome = "docked";
    spec.drawerMode = "wide";
    spec.graphPriority = "balanced";
    spec.palette = "caseboard";
    spec.investigationMode = "caseboard";
    matchedRules.push("case-board shell");
  }

  if (hasAny(normalized, ["keep the graph clean", "declutter the graph", "clean graph", "less clutter"])) {
    spec.graphPriority = "canvas";
    spec.chrome = "floating";
    spec.density = "compact";
    matchedRules.push("clean graph");
  }

  if (hasAny(normalized, ["show labels prominently", "labels first", "make labels obvious"])) {
    spec.graphPriority = "balanced";
    spec.drawerMode = "wide";
    spec.chrome = "docked";
    matchedRules.push("label-forward review");
  }

  if (hasAny(normalized, ["threat intel explorer", "threat intelligence", "show threat intel", "surface threat intel", "investigate exploits"])) {
    spec.tone = "executive";
    spec.density = "compact";
    spec.chrome = "docked";
    spec.drawerMode = "wide";
    spec.palette = "caseboard";
    spec.graphPriority = "balanced";
    spec.investigationMode = "threat";
    matchedRules.push("threat-intel explorer");
  }

  if (hasAny(normalized, ["prioritize suspicious counterparties", "show suspicious counterparties", "flag suspicious flows", "focus on risky counterparties"])) {
    spec.graphPriority = "balanced";
    spec.drawerMode = "wide";
    spec.density = "compact";
    spec.palette = "caseboard";
    spec.investigationMode = "threat";
    matchedRules.push("suspicious-counterparty focus");
  }

  if (hasAny(normalized, ["balanced", "split view"])) {
    spec.graphPriority = "balanced";
    matchedRules.push("balanced split");
  }

  if (hasAny(normalized, ["brief a client", "brief my team", "make this briefing ready", "make it presentation ready"])) {
    spec.tone = "executive";
    spec.graphPriority = "balanced";
    spec.chrome = "floating";
    spec.investigationMode = "briefing";
    matchedRules.push("briefing layout");
  }

  if (hasAny(normalized, ["wide drawer", "wide evidence drawer", "deeper drawer", "full evidence drawer"])) {
    spec.drawerMode = "wide";
    matchedRules.push("wide drawer");
  }

  if (hasAny(normalized, ["move transaction drawer to left side", "move drawer to left side", "move drawer left", "drawer on the left", "left-side drawer", "put the drawer on the left"])) {
    spec.drawerMode = "left";
    matchedRules.push("left drawer");
  }

  if (hasAny(normalized, ["move transaction drawer to bottom", "move drawer to bottom", "drawer on the bottom", "bottom drawer", "put the drawer at the bottom"])) {
    spec.drawerMode = "bottom";
    spec.graphPriority = "canvas";
    matchedRules.push("bottom drawer");
  }

  if (hasAny(normalized, ["right drawer", "standard drawer"])) {
    spec.drawerMode = "right";
    matchedRules.push("right drawer");
  }

  if (hasAny(normalized, ["angle nodes to the right on withdrawals", "put withdrawals on the right", "withdrawals right", "send outflows to the right"])) {
    spec.graphOrientation = "withdrawals-right";
    matchedRules.push("withdrawals-right graph");
  }

  if (hasAny(normalized, ["angle nodes to the right on deposits", "put deposits on the right", "deposits right", "send inflows to the right"])) {
    spec.graphOrientation = "deposits-right";
    matchedRules.push("deposits-right graph");
  }

  if (hasAny(normalized, ["pink and green", "pink & green", "pink green", "pink and mint", "pink & mint", "magenta and green"])) {
    spec.palette = "pinkmint";
    matchedRules.push("pink-mint palette");
  }

  return { spec, matchedRules };
}
