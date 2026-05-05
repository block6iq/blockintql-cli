export type GraphNodeTone = "seed" | "focus" | "artifact" | "query" | "entity";

export type GraphNode = {
  key: string;
  title: string;
  subtitle: string;
  rawValue: string;
  tone: GraphNodeTone;
  position?: {
    x: number;
    y: number;
  };
};

export type GraphEdge = {
  from: string;
  to: string;
  label?: string;
  direction?: "in" | "out";
  evidence?: string;
};

export type StepStatus = "queued" | "running" | "complete" | "failed" | "refunded";
export type StepSource = "planner" | "postgres" | "provider" | "workspace" | "shell";

export type OrchestrationStep = {
  id: string;
  label: string;
  detail: string;
  status: StepStatus;
  credits: number;
  usd: number;
  source: StepSource;
  focusNodeKey?: string;
  focusTransactionKeys?: string[];
  highlightEdges?: string[];
};

export type ExplorerTransaction = {
  date: string;
  txHash: string;
  flow: "in" | "out";
  asset: string;
  from: string;
  to: string;
  amount: number;
  evidence: string;
};

export type CounterpartySummary = {
  address: string;
  label: string;
  interactions: number;
  direction: "in" | "out" | "mixed";
};

export type ExplorerMetrics = {
  inboundUsd: number;
  outboundUsd: number;
  netUsd: number;
  transactions: number;
  firstActivity: string;
  lastActivity: string;
};

export type Holding = {
  symbol: string;
  balance: number;
  usd: number;
};

export type ExplorerNodeDetails = {
  address: string;
  dataSource: "mock" | "derived" | "live" | "fallback" | "degraded";
  backendSource?: string;
  warning?: string;
  historyWindowDays?: number;
  historyMode?: string;
  historyNote?: string;
  hotWallet?: boolean;
  hotWalletSource?: string;
  hotWalletEntity?: string;
  hotWalletCategory?: string;
  metrics: ExplorerMetrics;
  holdings: Holding[];
  transactions: ExplorerTransaction[];
  counterparties?: CounterpartySummary[];
};
