import type { ShellSpec } from "../shellSpec";
import { GraphCanvas } from "./GraphCanvas";
import type { GraphEdge, GraphNode } from "../types";

type GraphPanelProps = {
  workspaceName: string;
  workspaceGoal: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeKey: string;
  highlightedEdgeKeys: string[];
  shellSpec: ShellSpec;
  onSelectNode: (key: string) => void | Promise<void>;
};

export function GraphPanel({
  workspaceName,
  workspaceGoal,
  nodes,
  edges,
  selectedNodeKey,
  highlightedEdgeKeys,
  shellSpec,
  onSelectNode,
}: GraphPanelProps) {
  const isThreatMode = shellSpec.investigationMode === "threat";
  const laneLabels =
    shellSpec.graphOrientation === "deposits-right"
      ? {
          left: "Withdrawals",
          right: "Deposits",
        }
      : {
          left: "Inbound",
          right: "Withdrawals",
        };

  return (
    <section className="panel">
      <div className="graph-stage">
        <div className="graph-shell">
          <div className="graph-overlay">
            <div className="overlay-block graph-title-block">
              <div className="section-label">{isThreatMode ? "Threat Map //" : "Graph Explorer //"}</div>
              <strong>{workspaceName}</strong>
              <span>
                {isThreatMode
                  ? "Triage flagged relationships, labeled entities, and suspicious money movement."
                  : workspaceGoal}
              </span>
            </div>
            <div className="overlay-block graph-tip-block">
              <div className="section-label">{isThreatMode ? "Threat Review" : "Ready"}</div>
              <strong>
                {isThreatMode
                  ? "Open a node and prioritize labeled, suspicious, and exploit-linked evidence."
                  : "Select a node to inspect evidence."}
              </strong>
            </div>
          </div>
          <div className="lane-guides">
            <div className="lane-guide lane-guide-left">
              <span className="lane-guide-label">{laneLabels.left}</span>
            </div>
            <div className="lane-guide lane-guide-right">
              <span className="lane-guide-label">{laneLabels.right}</span>
            </div>
          </div>
          <div className="legend">
            <span style={{ color: "var(--mint)" }}>Seed</span>
            <span style={{ color: "var(--cyan)" }}>Focus</span>
            <span style={{ color: "var(--gold)" }}>Artifact</span>
            <span style={{ color: "var(--violet)" }}>Query</span>
            <span style={{ color: "var(--orange)" }}>Entity</span>
            {isThreatMode ? <span className="legend-mode-note">Threat mode</span> : null}
          </div>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            selectedNodeKey={selectedNodeKey}
            highlightedEdgeKeys={highlightedEdgeKeys}
            shellSpec={shellSpec}
            onSelectNode={onSelectNode}
          />
        </div>
      </div>
    </section>
  );
}
