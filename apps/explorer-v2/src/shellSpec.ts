export type ShellTone = "analyst" | "executive" | "builder";
export type ShellDensity = "compact" | "comfortable";
export type ShellChrome = "floating" | "docked";
export type GraphPriority = "canvas" | "balanced" | "table";
export type DrawerMode = "right" | "wide" | "left" | "bottom";
export type ShellPalette = "default" | "pinkmint" | "caseboard";
export type GraphOrientation = "auto" | "withdrawals-right" | "deposits-right";
export type InvestigationMode = "standard" | "moneyflow" | "triage" | "briefing" | "caseboard" | "threat";

export type ShellSpec = {
  tone: ShellTone;
  density: ShellDensity;
  chrome: ShellChrome;
  graphPriority: GraphPriority;
  drawerMode: DrawerMode;
  palette: ShellPalette;
  graphOrientation: GraphOrientation;
  investigationMode: InvestigationMode;
};

export const defaultShellSpec: ShellSpec = {
  tone: "analyst",
  density: "comfortable",
  chrome: "floating",
  graphPriority: "canvas",
  drawerMode: "right",
  palette: "default",
  graphOrientation: "auto",
  investigationMode: "standard",
};

export function shellSpecClassName(spec: ShellSpec) {
  return [
    `tone-${spec.tone}`,
    `density-${spec.density}`,
    `chrome-${spec.chrome}`,
    `priority-${spec.graphPriority}`,
    `drawer-${spec.drawerMode}`,
    `palette-${spec.palette}`,
    `graph-${spec.graphOrientation}`,
    `mode-${spec.investigationMode}`,
  ].join(" ");
}

export function shellSpecSummary(spec: ShellSpec) {
  return [
    `${spec.investigationMode} mode`,
    `${spec.tone} tone`,
    `${spec.density} density`,
    `${spec.chrome} chrome`,
    `${spec.graphPriority} graph priority`,
    `${spec.drawerMode} drawer`,
    `${spec.palette} palette`,
    `${spec.graphOrientation} graph orientation`,
  ].join(" · ");
}
