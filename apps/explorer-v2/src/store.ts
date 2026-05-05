import { create } from "zustand";
import { fetchLiveNodeDetails } from "./liveData";
import { mockDetails, mockEdges, mockNodes, mockSteps } from "./mockData";
import { compileShellPrompt } from "./prompting";
import { defaultShellSpec, type ShellSpec } from "./shellSpec";
import type { CounterpartySummary, ExplorerNodeDetails, ExplorerTransaction, GraphEdge, GraphNode, OrchestrationStep } from "./types";

const DEFAULT_API_BASE = "https://blockintql.com";
const INITIAL_WORKSPACE_ID = initialWorkspaceId();
const INITIAL_SEED_ADDRESS = initialSeedAddress();

function initialSearchParam(name: string) {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) || "";
}

function initialApiBase() {
  return initialSearchParam("apiBase") || DEFAULT_API_BASE;
}

function initialApiKey() {
  return initialSearchParam("api_key");
}

function initialWorkspaceId() {
  const paramValue = initialSearchParam("workspaceId");
  if (paramValue) return paramValue;
  if (typeof window === "undefined") return "";
  const match = window.location.pathname.match(/\/workspace\/([^/]+)\/explorer(?:-react)?$/);
  return match?.[1] || "";
}

function initialSeedAddress() {
  return initialSearchParam("address") || mockNodes[0]?.rawValue || "";
}

function initialWorkspaceName() {
  const explicit = initialSearchParam("workspaceName");
  if (explicit) return explicit;
  const workspaceId = initialWorkspaceId();
  if (workspaceId) return `Workspace ${workspaceId}`;
  return "BlockINTQL Explorer";
}

function initialWorkspaceGoal() {
  return (
    initialSearchParam("goal") ||
    "Investigation workspace for wallet evidence, triage, counterparties, and graph follow-up."
  );
}

function isAddressLike(rawValue: string) {
  return rawValue.startsWith("0x") && rawValue.length === 42;
}

function transactionKey(row: ExplorerTransaction) {
  return `${row.txHash}:${row.date}`;
}

function graphNodeKey(rawValue: string) {
  return `node:${rawValue.toLowerCase()}`;
}

function compactValue(rawValue: string) {
  if (rawValue.startsWith("0x") && rawValue.length > 12) {
    return `${rawValue.slice(0, 6)}...${rawValue.slice(-4)}`;
  }
  return rawValue;
}

function titleForSeedAddress(address: string) {
  return address ? compactValue(address) : "Seed";
}

function buildInitialNodes(seedAddress: string): GraphNode[] {
  const normalizedSeed = isAddressLike(seedAddress) ? seedAddress : mockNodes[0]?.rawValue || seedAddress;
  return mockNodes.map((node, index) =>
    index === 0
      ? {
          ...node,
          title: "Wallet",
          subtitle: titleForSeedAddress(normalizedSeed),
          rawValue: normalizedSeed,
        }
      : node,
  );
}

function buildInitialDetails(seedAddress: string): Record<string, ExplorerNodeDetails> {
  const normalizedSeed = isAddressLike(seedAddress) ? seedAddress : mockNodes[0]?.rawValue || seedAddress;
  const seedDetails = mockDetails.seed;
  return {
    ...mockDetails,
    seed: {
      ...seedDetails,
      address: normalizedSeed,
      counterparties: seedDetails.counterparties ? [...seedDetails.counterparties] : seedDetails.counterparties,
      holdings: [...seedDetails.holdings],
      transactions: seedDetails.transactions.map((row) => ({
        ...row,
        from: row.from.toLowerCase() === seedDetails.address.toLowerCase() ? normalizedSeed : row.from,
        to: row.to.toLowerCase() === seedDetails.address.toLowerCase() ? normalizedSeed : row.to,
      })),
    },
  };
}

function buildInitialSteps(seedAddress: string): OrchestrationStep[] {
  const subtitle = titleForSeedAddress(seedAddress);
  return mockSteps.map((step) => {
    if (step.id === "plan") {
      return {
        ...step,
        detail: `Mapped wallet history, evidence, and graph surfaces for ${subtitle}.`,
      };
    }
    if (step.id === "history") {
      return {
        ...step,
        detail: `Prepared a recent investigative slice for ${subtitle}.`,
      };
    }
    if (step.id === "drawer") {
      return {
        ...step,
        detail: `${subtitle} is ready in the analyst drawer for review and graph follow-up.`,
      };
    }
    return step;
  });
}

function edgeLabelForRow(row: ExplorerTransaction) {
  const amount =
    row.amount >= 1000
      ? new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(row.amount)
      : row.amount.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return `${row.asset} ${amount}`;
}

function nodeToneForValue(rawValue: string): GraphNode["tone"] {
  return rawValue.startsWith("0x") ? "entity" : "artifact";
}

function nodeTitleForValue(rawValue: string): GraphNode["title"] {
  return rawValue.startsWith("0x") ? compactValue(rawValue) : rawValue;
}

function findNextLanePosition(
  nodes: GraphNode[],
  baseNodeKey: string,
  side: "left" | "right",
  preferredY?: number,
) {
  const base = nodes.find((node) => node.key === baseNodeKey)?.position ?? { x: 0, y: 0 };
  const direction = side === "left" ? -1 : 1;
  const primaryLaneX = base.x + direction * 320;
  const laneNodes = nodes
    .map((node) => node.position)
    .filter((position): position is { x: number; y: number } => Boolean(position))
    .filter((position) => Math.abs(position.x - primaryLaneX) < 80);

  const slotOffsets = [0, -180, 180, -360, 360, -540, 540];

  if (typeof preferredY === "number") {
    const preferredTaken = laneNodes.some((position) => Math.abs(position.y - preferredY) < 40);
    if (!preferredTaken) {
      return { x: primaryLaneX, y: preferredY };
    }
  }

  for (let column = 0; column < 3; column += 1) {
    const laneX = primaryLaneX + direction * column * 220;
    const columnNodes = nodes
      .map((node) => node.position)
      .filter((position): position is { x: number; y: number } => Boolean(position))
      .filter((position) => Math.abs(position.x - laneX) < 80);

    for (const offset of slotOffsets) {
      const candidateY = base.y + offset;
      const occupied = columnNodes.some((position) => Math.abs(position.y - candidateY) < 40);
      if (!occupied) {
        return { x: laneX, y: candidateY };
      }
    }
  }

  return {
    x: primaryLaneX + direction * 440,
    y: base.y + 720,
  };
}

function sideForRow(row: ExplorerTransaction, selectedAddress: string, graphOrientation: ShellSpec["graphOrientation"]) {
  const lowerSelected = selectedAddress.toLowerCase();
  const isInbound = row.to.toLowerCase() === lowerSelected;
  if (graphOrientation === "deposits-right") {
    return isInbound ? "right" : "left";
  }
  return isInbound ? "left" : "right";
}

function allKnownTransactions(nodeDetails: Record<string, ExplorerNodeDetails>) {
  return Object.values(nodeDetails).flatMap((details) => details.transactions);
}

function summarizeCounterparties(address: string, transactions: ExplorerTransaction[]): CounterpartySummary[] {
  const lower = address.toLowerCase();
  const counterparties = new Map<string, CounterpartySummary>();

  for (const row of transactions) {
    const isInbound = row.to.toLowerCase() === lower;
    const counterparty = isInbound ? row.from : row.to;
    if (!counterparty || counterparty.toLowerCase() === lower) continue;
    const current = counterparties.get(counterparty) ?? {
      address: counterparty,
      label: compactValue(counterparty),
      interactions: 0,
      direction: isInbound ? ("in" as const) : ("out" as const),
    };
    current.interactions += 1;
    if ((current.direction === "in" && !isInbound) || (current.direction === "out" && isInbound)) {
      current.direction = "mixed";
    }
    counterparties.set(counterparty, current);
  }

  return Array.from(counterparties.values())
    .sort((a, b) => b.interactions - a.interactions)
    .slice(0, 8);
}

function deriveNodeDetailsFromTransactions(address: string, transactions: ExplorerTransaction[]): ExplorerNodeDetails {
  const relevant = transactions
    .filter((row) => row.from === address || row.to === address)
    .sort((a, b) => Date.parse(b.date) - Date.parse(a.date));

  const inboundRows = relevant.filter((row) => row.to === address);
  const outboundRows = relevant.filter((row) => row.from === address);

  const inboundUsd = inboundRows.reduce((sum, row) => sum + (row.asset === "USDC" ? row.amount : 0), 0);
  const outboundUsd = outboundRows.reduce((sum, row) => sum + (row.asset === "USDC" ? row.amount : 0), 0);

  const holdingsMap = new Map<string, { balance: number; usd: number }>();
  for (const row of inboundRows) {
    const existing = holdingsMap.get(row.asset) ?? { balance: 0, usd: 0 };
    const nextBalance = existing.balance + row.amount;
    const nextUsd = existing.usd + (row.asset === "USDC" ? row.amount : 0);
    holdingsMap.set(row.asset, { balance: nextBalance, usd: nextUsd });
  }
  for (const row of outboundRows) {
    const existing = holdingsMap.get(row.asset) ?? { balance: 0, usd: 0 };
    const nextBalance = Math.max(0, existing.balance - row.amount);
    const nextUsd = Math.max(0, existing.usd - (row.asset === "USDC" ? row.amount : 0));
    holdingsMap.set(row.asset, { balance: nextBalance, usd: nextUsd });
  }

  const dates = relevant
    .map((row) => Date.parse(row.date))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);

  return {
    address,
    dataSource: "derived",
    metrics: {
      inboundUsd,
      outboundUsd,
      netUsd: inboundUsd - outboundUsd,
      transactions: relevant.length,
      firstActivity: dates.length ? new Date(dates[0]).toISOString() : "",
      lastActivity: dates.length ? new Date(dates[dates.length - 1]).toISOString() : "",
    },
    holdings: Array.from(holdingsMap.entries()).map(([symbol, value]) => ({
      symbol,
      balance: value.balance,
      usd: value.usd,
    })),
    transactions: relevant,
    counterparties: summarizeCounterparties(address, relevant),
  };
}

function materializeNodeDetails(state: Pick<ExplorerState, "nodeDetails" | "nodes">, nodeKey: string) {
  const existing = state.nodeDetails[nodeKey];
  if (existing) return existing;

  const node = state.nodes.find((entry) => entry.key === nodeKey);
  if (!node) return null;

  const transactions = allKnownTransactions(state.nodeDetails);
  if (!transactions.length) return null;

  return deriveNodeDetailsFromTransactions(node.rawValue, transactions);
}

type ExplorerState = {
  apiBase: string;
  apiKey: string;
  workspaceId: string;
  workspaceName: string;
  workspaceGoal: string;
  graphState: string;
  artifactCount: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeKey: string;
  nodeDetails: Record<string, ExplorerNodeDetails>;
  selectedTransactionKeys: Record<string, string[]>;
  steps: OrchestrationStep[];
  activeStepId: string | null;
  highlightedEdgeKeys: string[];
  focusedTransactionKey: string | null;
  loadingNodeKey: string | null;
  shellPrompt: string;
  shellSpec: ShellSpec;
  matchedShellRules: string[];
  setApiKey: (value: string) => void;
  setSelectedNodeKey: (key: string) => Promise<void>;
  loadWorkspace: () => Promise<void>;
  clearWorkspace: () => void;
  runAddressHistory: () => void;
  hydrateGraph: () => void;
  saveView: () => void;
  focusStep: (stepId: string) => void;
  focusTransaction: (nodeKey: string, txKey: string) => void;
  traceTransaction: (nodeKey: string, txKey: string) => Promise<void>;
  openTransactionCounterparty: (nodeKey: string, txKey: string, side: "from" | "to") => Promise<void>;
  toggleTransactionSelection: (nodeKey: string, txKey: string) => void;
  selectAllTransactions: (nodeKey: string) => void;
  clearTransactionSelection: (nodeKey: string) => void;
  plotSelectedTransactions: (nodeKey: string) => void;
  expandCounterparties: (nodeKey: string) => void;
  setShellPrompt: (value: string) => void;
  applyShellPrompt: () => void;
};

type WorkspaceManifest = {
  workspace?: {
    workspace_id?: string;
    name?: string;
  };
  context?: {
    seed?: {
      goal?: string;
      address?: string;
    };
  };
  runtime?: {
    ready?: boolean;
  };
  warehouse?: {
    recent_queries?: Array<unknown>;
  };
};

async function fetchWorkspaceManifest(apiBase: string, workspaceId: string, apiKey: string): Promise<WorkspaceManifest | null> {
  if (!workspaceId || !apiKey) return null;
  const response = await fetch(`${apiBase}/v1/workspaces/${workspaceId}/manifest`, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) {
    return null;
  }
  return response.json();
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  apiBase: initialApiBase(),
  apiKey: initialApiKey(),
  workspaceId: INITIAL_WORKSPACE_ID,
  workspaceName: initialWorkspaceName(),
  workspaceGoal: initialWorkspaceGoal(),
  graphState: "Seed only",
  artifactCount: 0,
  nodes: buildInitialNodes(INITIAL_SEED_ADDRESS),
  edges: mockEdges,
  selectedNodeKey: "seed",
  nodeDetails: buildInitialDetails(INITIAL_SEED_ADDRESS),
  selectedTransactionKeys: {},
  steps: buildInitialSteps(INITIAL_SEED_ADDRESS),
  activeStepId: "history",
  highlightedEdgeKeys: ["cp-1->seed"],
  focusedTransactionKey: "0x02ec88f471111111111111111111111111111111111111111111111111111111:2025-12-06T11:11:00Z",
  loadingNodeKey: null,
  shellPrompt: "Build a graph-first analyst workstation with floating controls and a right-side evidence drawer.",
  shellSpec: defaultShellSpec,
  matchedShellRules: [],
  setApiKey: (value) => set({ apiKey: value }),
  setSelectedNodeKey: async (key) => {
    const state = useExplorerStore.getState();
    const node = state.nodes.find((entry) => entry.key === key);
    const derived = materializeNodeDetails(state, key);

    set({
      selectedNodeKey: key,
      activeStepId: null,
      highlightedEdgeKeys: [],
      focusedTransactionKey: null,
      loadingNodeKey: isAddressLike(node?.rawValue || "") && Boolean(state.apiKey) ? key : null,
      nodeDetails: derived
        ? {
            ...state.nodeDetails,
            [key]: derived,
          }
        : state.nodeDetails,
    });

    if (!node || !isAddressLike(node.rawValue) || !state.apiKey) {
      set({ loadingNodeKey: null });
      return;
    }

    const fetchStepId = `fetch-node:${key}`;
    set((current) => ({
      activeStepId: fetchStepId,
      steps: [
        ...current.steps.filter((step) => step.id !== fetchStepId),
        {
          id: fetchStepId,
          label: "Loaded live node evidence",
          detail: `Fetching live address history, balances, and stats for ${node.subtitle || node.rawValue}.`,
          status: "running",
          credits: 0,
          usd: 0,
          source: "provider",
          focusNodeKey: key,
        },
      ],
    }));

    try {
      const liveDetails = await fetchLiveNodeDetails(state.apiBase, state.apiKey, node.rawValue);
      set((current) => ({
        nodeDetails: {
          ...current.nodeDetails,
          [key]: liveDetails,
        },
        loadingNodeKey: null,
        activeStepId: fetchStepId,
        steps: current.steps.map((step) =>
          step.id === fetchStepId
            ? {
                ...step,
                status: "complete",
                source: liveDetails.backendSource === "postgres" ? "postgres" : "provider",
                detail:
                  liveDetails.dataSource === "degraded"
                    ? `${liveDetails.warning || "Live node evidence degraded cleanly."} Source: ${liveDetails.backendSource || "unknown"}.`
                    : `Loaded ${liveDetails.metrics.transactions} live transaction rows and wallet balances for ${node.subtitle || node.rawValue}.`,
              }
            : step,
        ),
      }));
      return;
    } catch (error) {
      set((current) => ({
        loadingNodeKey: null,
        activeStepId: fetchStepId,
        steps: current.steps.map((step) =>
          step.id === fetchStepId
            ? {
                ...step,
                status: "failed",
                source: "shell",
                detail: derived
                  ? `Live fetch failed, so the drawer fell back to evidence already loaded into the shell.`
                  : `Live fetch failed and no loaded evidence was available for fallback.`,
              }
            : step,
        ),
      }));
      return;
    }
  },
  loadWorkspace: async () => {
    const state = useExplorerStore.getState();
    const manifest = await fetchWorkspaceManifest(state.apiBase, state.workspaceId, state.apiKey);
    const manifestSeed = manifest?.context?.seed?.address;
    const seedAddress = manifestSeed && isAddressLike(manifestSeed) ? manifestSeed : state.nodes[0]?.rawValue || INITIAL_SEED_ADDRESS;
    const workspaceName = manifest?.workspace?.name || state.workspaceName;
    const workspaceGoal = manifest?.context?.seed?.goal || state.workspaceGoal;
    const recentQueries = manifest?.warehouse?.recent_queries || [];
    const graphState = manifest
      ? manifest.runtime?.ready
        ? `Workspace ${manifest.workspace?.workspace_id || state.workspaceId} ready`
        : `Workspace ${manifest.workspace?.workspace_id || state.workspaceId} provisioning`
      : state.workspaceId
        ? `Workspace ${state.workspaceId} ready`
        : "Seed ready · history loaded";

    set(() => ({
      workspaceName,
      workspaceGoal,
      graphState,
      artifactCount: recentQueries.length,
      nodes: buildInitialNodes(seedAddress),
      nodeDetails: buildInitialDetails(seedAddress),
      steps: buildInitialSteps(seedAddress),
      selectedNodeKey: "seed",
      activeStepId: "history",
      highlightedEdgeKeys: ["cp-1->seed"],
      focusedTransactionKey: "0x02ec88f471111111111111111111111111111111111111111111111111111111:2025-12-06T11:11:00Z",
    }));
    await useExplorerStore.getState().setSelectedNodeKey("seed");
  },
  clearWorkspace: () =>
    set((state) => ({
      selectedNodeKey: "seed",
      selectedTransactionKeys: {},
      activeStepId: null,
      highlightedEdgeKeys: [],
      focusedTransactionKey: null,
      graphState: "Seed only",
      steps: state.steps.map((step) =>
        step.id === "plot"
          ? {
              ...step,
              status: "queued" as const,
              detail: "Choose evidence rows to add counterparties and edges to the graph.",
            }
          : step,
      ),
    })),
  runAddressHistory: () =>
    set((state) => {
      const step = state.steps.find((entry) => entry.id === "history");
      if (!step) return state;
      return {
        activeStepId: "history",
        selectedNodeKey: step.focusNodeKey ?? state.selectedNodeKey,
        highlightedEdgeKeys: step.highlightEdges ?? [],
        focusedTransactionKey: step.focusTransactionKeys?.[0] ?? null,
        selectedTransactionKeys: step.focusNodeKey && step.focusTransactionKeys
          ? {
              ...state.selectedTransactionKeys,
              [step.focusNodeKey]: step.focusTransactionKeys,
            }
          : state.selectedTransactionKeys,
      };
    }),
  hydrateGraph: () =>
    set((state) => {
      const hydrateStep: OrchestrationStep = {
        id: "hydrate",
        label: "Hydrated graph surface",
        detail: "Refreshed graph relationships and replay-ready highlights from the current investigation state.",
        status: "complete",
        credits: 0,
        usd: 0,
        source: "shell",
        focusNodeKey: state.selectedNodeKey,
        highlightEdges: state.highlightedEdgeKeys,
      };
      return {
        activeStepId: "hydrate",
        steps: [...state.steps.filter((step) => step.id !== "hydrate"), hydrateStep],
      };
    }),
  saveView: () =>
    set((state) => {
      const saveStep: OrchestrationStep = {
        id: "save-view",
        label: "Saved explorer view",
        detail: "Captured the current graph focus, drawer state, and investigation rail as a local view snapshot.",
        status: "complete",
        credits: 0,
        usd: 0,
        source: "shell",
        focusNodeKey: state.selectedNodeKey,
        highlightEdges: state.highlightedEdgeKeys,
      };
      return {
        activeStepId: "save-view",
        steps: [...state.steps.filter((step) => step.id !== "save-view"), saveStep],
      };
    }),
  focusStep: (stepId) =>
    set((state) => {
      const step = state.steps.find((entry) => entry.id === stepId);
      if (!step?.focusNodeKey) return state;
      const derived = materializeNodeDetails(state, step.focusNodeKey);
      return {
        selectedNodeKey: step.focusNodeKey,
        activeStepId: stepId,
        highlightedEdgeKeys: step.highlightEdges ?? [],
        focusedTransactionKey: step.focusTransactionKeys?.[0] ?? null,
        selectedTransactionKeys: step.focusTransactionKeys
          ? {
              ...state.selectedTransactionKeys,
              [step.focusNodeKey]: step.focusTransactionKeys,
            }
          : state.selectedTransactionKeys,
        nodeDetails: derived
          ? {
              ...state.nodeDetails,
              [step.focusNodeKey]: derived,
            }
          : state.nodeDetails,
      };
    }),
  focusTransaction: (nodeKey, txKey) =>
    set((state) => {
      const details = state.nodeDetails[nodeKey];
      if (!details) return state;
      const row = details.transactions.find((entry) => transactionKey(entry) === txKey);
      if (!row) return state;
      const fromKey = row.from.toLowerCase() === details.address.toLowerCase() ? nodeKey : graphNodeKey(row.from);
      const toKey = row.to.toLowerCase() === details.address.toLowerCase() ? nodeKey : graphNodeKey(row.to);
      return {
        selectedNodeKey: nodeKey,
        focusedTransactionKey: txKey,
        highlightedEdgeKeys: [`${fromKey}->${toKey}`],
      };
    }),
  traceTransaction: async (nodeKey, txKey) => {
    const state = useExplorerStore.getState();
    const details = state.nodeDetails[nodeKey];
    const row = details?.transactions.find((entry) => transactionKey(entry) === txKey);
    if (!details || !row) return;

    const nextNodes = [...state.nodes];
    const nextNodeDetails = { ...state.nodeDetails };
    const existingNodeKeys = new Set(nextNodes.map((node) => node.key));
    const endpoints = [
      { value: row.from, isSelected: row.from.toLowerCase() === details.address.toLowerCase(), side: "left" as const },
      { value: row.to, isSelected: row.to.toLowerCase() === details.address.toLowerCase(), side: "right" as const },
    ];

    for (const endpoint of endpoints) {
      if (endpoint.isSelected || !isAddressLike(endpoint.value)) continue;
      const key = graphNodeKey(endpoint.value);
      if (!existingNodeKeys.has(key)) {
        nextNodes.push({
          key,
          title: nodeTitleForValue(endpoint.value),
          subtitle: compactValue(endpoint.value),
          rawValue: endpoint.value,
          tone: nodeToneForValue(endpoint.value),
          position: findNextLanePosition(nextNodes, nodeKey, endpoint.side, row.date ? Date.parse(row.date) % 360 : undefined),
        });
        existingNodeKeys.add(key);
      }
      if (!nextNodeDetails[key]) {
        nextNodeDetails[key] = deriveNodeDetailsFromTransactions(endpoint.value, [
          ...allKnownTransactions(nextNodeDetails),
          row,
        ]);
      }
    }

    const fromKey = row.from.toLowerCase() === details.address.toLowerCase() ? nodeKey : graphNodeKey(row.from);
    const toKey = row.to.toLowerCase() === details.address.toLowerCase() ? nodeKey : graphNodeKey(row.to);
    const highlightEdge = `${fromKey}->${toKey}`;

    set((current) => ({
      nodes: nextNodes,
      nodeDetails: nextNodeDetails,
      selectedNodeKey: nodeKey,
      activeStepId: "trace-transaction",
      focusedTransactionKey: txKey,
      highlightedEdgeKeys: [highlightEdge],
      selectedTransactionKeys: {
        ...current.selectedTransactionKeys,
        [nodeKey]: [txKey],
      },
      steps: [
        ...current.steps.filter((step) => step.id !== "trace-transaction"),
        {
          id: "trace-transaction",
          label: "Traced transaction path",
          detail: `Highlighted ${row.asset} movement from ${compactValue(row.from)} to ${compactValue(row.to)}.`,
          status: "complete",
          credits: 0,
          usd: 0,
          source: "shell",
          focusNodeKey: nodeKey,
          focusTransactionKeys: [txKey],
          highlightEdges: [highlightEdge],
        },
      ],
    }));
  },
  openTransactionCounterparty: async (nodeKey, txKey, side) => {
    const state = useExplorerStore.getState();
    const details = state.nodeDetails[nodeKey];
    const row = details?.transactions.find((entry) => transactionKey(entry) === txKey);
    if (!details || !row) return;

    const candidate = side === "from" ? row.from : row.to;
    if (!isAddressLike(candidate) || candidate.toLowerCase() === details.address.toLowerCase()) return;

    const key = graphNodeKey(candidate);
    if (!state.nodes.find((entry) => entry.key === key)) {
      const laneSide = side === "from" ? "left" : "right";
      set((current) => ({
        nodes: [
          ...current.nodes,
          {
            key,
            title: nodeTitleForValue(candidate),
            subtitle: compactValue(candidate),
            rawValue: candidate,
            tone: nodeToneForValue(candidate),
            position: findNextLanePosition(current.nodes, nodeKey, laneSide),
          },
        ],
      }));
    }

    await useExplorerStore.getState().setSelectedNodeKey(key);
  },
  toggleTransactionSelection: (nodeKey, txKey) =>
    set((state) => {
      const current = state.selectedTransactionKeys[nodeKey] ?? [];
      const next = current.includes(txKey)
        ? current.filter((value) => value !== txKey)
        : [...current, txKey];
      return {
        selectedTransactionKeys: {
          ...state.selectedTransactionKeys,
          [nodeKey]: next,
        },
        activeStepId: "plot",
        highlightedEdgeKeys: [],
        focusedTransactionKey: txKey,
        steps: state.steps.map((step) =>
          step.id === "plot"
            ? {
                ...step,
                status: next.length ? ("running" as const) : ("queued" as const),
                detail: next.length
                  ? `${next.length} selected transfer${next.length === 1 ? "" : "s"} ready to plot from the drawer.`
                  : "Choose evidence rows to add counterparties and edges to the graph.",
              }
            : step,
        ),
      };
    }),
  selectAllTransactions: (nodeKey) =>
    set((state) => {
      const details = state.nodeDetails[nodeKey];
      if (!details) return state;
      return {
        selectedTransactionKeys: {
          ...state.selectedTransactionKeys,
          [nodeKey]: details.transactions.map(transactionKey),
        },
        activeStepId: "plot",
        highlightedEdgeKeys: [],
        focusedTransactionKey: details.transactions[0] ? transactionKey(details.transactions[0]) : null,
        steps: state.steps.map((step) =>
          step.id === "plot"
            ? {
                ...step,
                status: details.transactions.length ? ("running" as const) : ("queued" as const),
                detail: details.transactions.length
                  ? `Selected all ${details.transactions.length} transfer${details.transactions.length === 1 ? "" : "s"} for plotting.`
                  : "Choose evidence rows to add counterparties and edges to the graph.",
              }
            : step,
        ),
      };
    }),
  clearTransactionSelection: (nodeKey) =>
    set((state) => ({
      selectedTransactionKeys: {
        ...state.selectedTransactionKeys,
        [nodeKey]: [],
      },
      activeStepId: "plot",
      highlightedEdgeKeys: [],
      focusedTransactionKey: null,
      steps: state.steps.map((step) =>
        step.id === "plot"
          ? {
              ...step,
              status: "queued" as const,
              detail: "Choose evidence rows to add counterparties and edges to the graph.",
            }
          : step,
      ),
    })),
  plotSelectedTransactions: (nodeKey) =>
    set((state) => {
      const details = state.nodeDetails[nodeKey];
      const selectedKeys = state.selectedTransactionKeys[nodeKey] ?? [];
      if (!details || !selectedKeys.length) return state;

      const selectedRows = details.transactions.filter((row) => selectedKeys.includes(transactionKey(row)));
      if (!selectedRows.length) return state;

      const existingNodeKeys = new Set(state.nodes.map((node) => node.key));
      const existingEdges = new Set(state.edges.map((edge) => `${edge.from}->${edge.to}`));
      const nextNodes = [...state.nodes];
      const nextEdges = [...state.edges];
      const nextNodeDetails = { ...state.nodeDetails };
      let addedNodes = 0;
      let addedEdges = 0;

      for (const row of selectedRows) {
        const endpoints = [
          { value: row.from, isSelected: row.from === details.address, role: "from" as const },
          { value: row.to, isSelected: row.to === details.address, role: "to" as const },
        ];

        for (const endpoint of endpoints) {
          if (endpoint.isSelected) continue;
          const key = graphNodeKey(endpoint.value);
          if (!existingNodeKeys.has(key)) {
            const side = sideForRow(row, details.address, state.shellSpec.graphOrientation);
            nextNodes.push({
              key,
              title: nodeTitleForValue(endpoint.value),
              subtitle: compactValue(endpoint.value),
              rawValue: endpoint.value,
              tone: nodeToneForValue(endpoint.value),
              position: findNextLanePosition(nextNodes, nodeKey, side),
            });
            existingNodeKeys.add(key);
            addedNodes += 1;
          }

          if (!nextNodeDetails[key]) {
            nextNodeDetails[key] = deriveNodeDetailsFromTransactions(endpoint.value, [
              ...allKnownTransactions(nextNodeDetails),
              ...selectedRows,
            ]);
          }
        }

        const fromKey = row.from === details.address ? nodeKey : graphNodeKey(row.from);
        const toKey = row.to === details.address ? nodeKey : graphNodeKey(row.to);
        const edgeKey = `${fromKey}->${toKey}`;
        if (!existingEdges.has(edgeKey)) {
          nextEdges.push({
            from: fromKey,
            to: toKey,
            label: edgeLabelForRow(row),
            direction: row.flow,
            evidence: row.evidence,
          });
          existingEdges.add(edgeKey);
          addedEdges += 1;
        }
      }

      const summaryParts = [];
      if (addedNodes) summaryParts.push(`${addedNodes} node${addedNodes === 1 ? "" : "s"}`);
      if (addedEdges) summaryParts.push(`${addedEdges} edge${addedEdges === 1 ? "" : "s"}`);
      const graphState = summaryParts.length
        ? `Plotted ${summaryParts.join(" · ")} from ${selectedRows.length} selected transfer${selectedRows.length === 1 ? "" : "s"}`
        : `Selected ${selectedRows.length} transfer${selectedRows.length === 1 ? "" : "s"} already plotted`;

      return {
        nodes: nextNodes,
        edges: nextEdges,
        nodeDetails: nextNodeDetails,
        graphState,
        activeStepId: "plot-result",
        highlightedEdgeKeys: selectedRows.map((row) => {
          const fromKey = row.from === details.address ? nodeKey : graphNodeKey(row.from);
          const toKey = row.to === details.address ? nodeKey : graphNodeKey(row.to);
          return `${fromKey}->${toKey}`;
        }),
        focusedTransactionKey: selectedKeys[0] ?? null,
        steps: [
          ...state.steps.filter((step) => step.id !== "plot-result"),
          ...state.steps.map((step) =>
            step.id === "plot"
              ? {
                  ...step,
                  status: "complete" as const,
                  detail: graphState,
                }
              : step,
          ),
          {
            id: "plot-result",
            label: "Updated graph from selected evidence",
            detail: graphState,
            status: "complete",
            credits: 0,
            usd: 0,
            source: "shell",
            focusNodeKey: nodeKey,
            focusTransactionKeys: selectedKeys,
            highlightEdges: selectedRows.map((row) => {
              const fromKey = row.from === details.address ? nodeKey : graphNodeKey(row.from);
              const toKey = row.to === details.address ? nodeKey : graphNodeKey(row.to);
              return `${fromKey}->${toKey}`;
            }),
          },
        ],
      };
    }),
  expandCounterparties: (nodeKey) =>
    set((state) => {
      const details = state.nodeDetails[nodeKey];
      if (!details) return state;

      const selectedKeys = details.transactions.map(transactionKey);
      const selectedRows = details.transactions;
      if (!selectedRows.length) return state;

      const existingNodeKeys = new Set(state.nodes.map((node) => node.key));
      const existingEdges = new Set(state.edges.map((edge) => `${edge.from}->${edge.to}`));
      const nextNodes = [...state.nodes];
      const nextEdges = [...state.edges];
      const nextNodeDetails = { ...state.nodeDetails };
      let addedNodes = 0;
      let addedEdges = 0;

      for (const row of selectedRows) {
        const endpoints = [
          { value: row.from, isSelected: row.from === details.address },
          { value: row.to, isSelected: row.to === details.address },
        ];

        for (const endpoint of endpoints) {
          if (endpoint.isSelected) continue;
          const key = graphNodeKey(endpoint.value);
          if (!existingNodeKeys.has(key)) {
            const side = sideForRow(row, details.address, state.shellSpec.graphOrientation);
            nextNodes.push({
              key,
              title: nodeTitleForValue(endpoint.value),
              subtitle: compactValue(endpoint.value),
              rawValue: endpoint.value,
              tone: nodeToneForValue(endpoint.value),
              position: findNextLanePosition(nextNodes, nodeKey, side),
            });
            existingNodeKeys.add(key);
            addedNodes += 1;
          }

          if (!nextNodeDetails[key]) {
            nextNodeDetails[key] = deriveNodeDetailsFromTransactions(endpoint.value, [
              ...allKnownTransactions(nextNodeDetails),
              ...selectedRows,
            ]);
          }
        }

        const fromKey = row.from === details.address ? nodeKey : graphNodeKey(row.from);
        const toKey = row.to === details.address ? nodeKey : graphNodeKey(row.to);
        const edgeKey = `${fromKey}->${toKey}`;
        if (!existingEdges.has(edgeKey)) {
          nextEdges.push({
            from: fromKey,
            to: toKey,
            label: edgeLabelForRow(row),
            direction: row.flow,
            evidence: row.evidence,
          });
          existingEdges.add(edgeKey);
          addedEdges += 1;
        }
      }

      const graphState = `Expanded ${addedNodes} counterparty node${addedNodes === 1 ? "" : "s"} and ${addedEdges} edge${addedEdges === 1 ? "" : "s"} from full node history`;
      const highlightEdges = selectedRows.map((row) => {
        const fromKey = row.from === details.address ? nodeKey : graphNodeKey(row.from);
        const toKey = row.to === details.address ? nodeKey : graphNodeKey(row.to);
        return `${fromKey}->${toKey}`;
      });

      const expandStep: OrchestrationStep = {
        id: "expand-counterparties",
        label: "Expanded counterparties",
        detail: graphState,
        status: "complete",
        credits: 0,
        usd: 0,
        source: "shell",
        focusNodeKey: nodeKey,
        focusTransactionKeys: selectedKeys,
        highlightEdges,
      };

      return {
        nodes: nextNodes,
        edges: nextEdges,
        nodeDetails: nextNodeDetails,
        selectedTransactionKeys: {
          ...state.selectedTransactionKeys,
          [nodeKey]: selectedKeys,
        },
        highlightedEdgeKeys: highlightEdges,
        focusedTransactionKey: selectedKeys[0] ?? null,
        graphState,
        activeStepId: "expand-counterparties",
        steps: [...state.steps.filter((step) => step.id !== "expand-counterparties"), expandStep],
      };
    }),
  setShellPrompt: (value) => set({ shellPrompt: value }),
  applyShellPrompt: () =>
    set((state) => {
      const compiled = compileShellPrompt(state.shellPrompt);
      return {
        shellSpec: compiled.spec,
        matchedShellRules: compiled.matchedRules,
      };
    }),
}));
