import { useEffect, useMemo, useRef } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";
import type { ShellSpec } from "../shellSpec";
import type { GraphEdge, GraphNode } from "../types";

type GraphCanvasProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeKey: string;
  highlightedEdgeKeys: string[];
  shellSpec: ShellSpec;
  onSelectNode: (key: string) => void | Promise<void>;
};

const toneColor: Record<GraphNode["tone"], string> = {
  seed: "#8dffd1",
  focus: "#6cecff",
  artifact: "#f0c94b",
  query: "#c085ff",
  entity: "#ffad61",
};

export function GraphCanvas({
  nodes,
  edges,
  selectedNodeKey,
  highlightedEdgeKeys,
  shellSpec,
  onSelectNode,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const isThreatMode = shellSpec.investigationMode === "threat";

  const elements = useMemo(
    () => [
      ...nodes.map((node) => ({
        data: {
          id: node.key,
          label: node.title,
          subtitle: node.subtitle,
          tone: node.tone,
          color: toneColor[node.tone],
        },
        position: node.position,
      })),
      ...edges.map((edge, index) => ({
        data: {
          id: `edge-${index}`,
          source: edge.from,
          target: edge.to,
          edgeKey: `${edge.from}->${edge.to}`,
          label: edge.label ?? "",
          direction: edge.direction ?? "",
          evidence: edge.evidence ?? "",
        },
      })),
    ],
    [edges, nodes],
  );

  const stylesheet = useMemo(
    () => [
      {
        selector: "node",
        style: {
          "background-color": "data(color)",
          label: "data(label)",
          color: "#f7fbff",
          "font-size": 18,
          "font-weight": 800,
          "text-valign": "center",
          "text-halign": "center",
          "text-wrap": "wrap",
          "text-max-width": 120,
          width: 110,
          height: 110,
          "border-width": 3,
          "border-color": "#effcff",
          "overlay-opacity": 0,
        },
      },
      ...(isThreatMode
        ? [
            {
              selector: 'node[tone = "entity"]',
              style: {
                "border-color": "#ffd977",
                "border-width": 4,
              },
            },
            {
              selector: 'node[tone = "artifact"]',
              style: {
                "border-color": "#ff9f80",
              },
            },
          ]
        : []),
      {
        selector: "node:selected",
        style: {
          "shadow-blur": 28,
          "shadow-color": isThreatMode ? "#ffd977" : "#8dffd1",
          "shadow-opacity": 0.45,
          "border-color": isThreatMode ? "#ffd977" : "#8dffd1",
        } as never,
      },
      {
        selector: "edge",
        style: {
          width: isThreatMode ? 3.5 : 3,
          "line-color": isThreatMode ? "rgba(166, 232, 255, 0.45)" : "rgba(108,236,255,0.55)",
          "target-arrow-color": isThreatMode ? "rgba(166, 232, 255, 0.45)" : "rgba(108,236,255,0.55)",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          color: isThreatMode ? "rgba(255, 230, 164, 0.95)" : "rgba(186, 235, 255, 0.92)",
          "font-size": isThreatMode ? 10 : 9,
          "font-family": "SFMono-Regular, Menlo, Monaco, monospace",
          "text-background-color": "rgba(5, 12, 21, 0.92)",
          "text-background-opacity": 1,
          "text-background-padding": 3,
          "text-border-width": 1,
          "text-border-color": "rgba(255,255,255,0.04)",
          "text-rotation": "autorotate",
          "text-margin-y": -10,
        },
      },
      {
        selector: 'edge[direction = "out"]',
        style: {
          "line-color": "rgba(255,171,104,0.72)",
          "target-arrow-color": "rgba(255,171,104,0.72)",
        },
      },
      {
        selector: 'edge[evidence = "labeled"]',
        style: {
          "line-style": "solid",
          width: isThreatMode ? 4.5 : 3.5,
          "line-color": isThreatMode ? "#f5cb65" : undefined,
          "target-arrow-color": isThreatMode ? "#f5cb65" : undefined,
        },
      },
      {
        selector: 'edge[evidence = "unverified"]',
        style: {
          "line-style": "dashed",
          opacity: isThreatMode ? 0.8 : 1,
        },
      },
      {
        selector: "edge.highlighted",
        style: {
          width: 5,
          "line-color": "#f5cb65",
          "target-arrow-color": "#f5cb65",
          color: "#ffd977",
          "font-size": 10,
        },
      },
    ],
    [isThreatMode],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const previousPan = cyRef.current?.pan();
    const previousZoom = cyRef.current?.zoom();
    cyRef.current?.destroy();
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: stylesheet as never,
      layout: {
        name: "preset",
        fit: !previousPan,
        padding: 80,
      },
    });
    if (previousPan && previousZoom) {
      cy.zoom(previousZoom);
      cy.pan(previousPan);
    }
    cy.on("tap", "node", (event) => {
      onSelectNode(event.target.id());
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [elements, onSelectNode, shellSpec.graphOrientation, stylesheet]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().unselect();
    const node = cy.getElementById(selectedNodeKey);
    if (node) {
      node.select();
    }
  }, [selectedNodeKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().removeClass("highlighted");
    if (!highlightedEdgeKeys.length) return;
    cy.edges().forEach((edge) => {
      const edgeKey = edge.data("edgeKey");
      if (highlightedEdgeKeys.includes(edgeKey)) {
        edge.addClass("highlighted");
      }
    });
  }, [highlightedEdgeKeys]);

  return <div className="graph-canvas-react" ref={containerRef} />;
}
