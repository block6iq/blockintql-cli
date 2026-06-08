import type { CounterpartySummary, ExplorerNodeDetails, ExplorerTransaction } from "./types";

type ApiEnvelope<T> = {
  data?: T;
  source?: string;
  warning?: string;
  count?: number;
  window_days?: number;
  hot_wallet?: boolean;
  hot_wallet_source?: string;
  hot_wallet_entity?: string;
  hot_wallet_category?: string;
  history_mode?: string;
  history_note?: string;
};

type HistoryRow = {
  tx_hash?: string;
  block_time?: string;
  from_address?: string;
  to_address?: string;
  amount?: number | string;
  token_symbol?: string | null;
  status?: string;
  type?: string;
};

type StablecoinPayload = {
  address?: string;
  stablecoin_balances?: Record<string, { balance?: number; contract?: string; decimals?: number }>;
  wallet_total_usd?: number;
};

type StatsPayload = {
  address?: string;
  transactions?: {
    total?: number;
    sent?: number;
    received?: number;
  };
  volume?: {
    total_stablecoin_sent_usd?: number;
    total_stablecoin_received_usd?: number;
  };
  activity?: {
    first_transaction?: string;
    last_transaction?: string;
  };
};

type StablecoinCounterpartyPayload = {
  address?: string;
  counterparties?: Array<{
    counterparty?: string;
    direction?: "inbound" | "outbound" | "both";
    tx_count?: number;
  }>;
};

function toNumber(value: unknown) {
  const num = typeof value === "number" ? value : Number(value ?? 0);
  return Number.isFinite(num) ? num : 0;
}

function normalizeHistoryRow(address: string, row: HistoryRow): ExplorerTransaction {
  const from = String(row.from_address || "");
  const to = String(row.to_address || "");
  const asset = String(row.token_symbol || (row.type === "native" ? "ETH" : "TOKEN"));
  const evidence = String(row.status || "indexed").toLowerCase();

  const flow = to.toLowerCase() === address.toLowerCase() ? "in" : "out";
  const amt = toNumber(row.amount);
  // Simple usd estimate for stablecoins / common tokens (real server provides better)
  const usd = /usdc|usdt|dai|busd/i.test(asset) ? amt : undefined;

  return {
    date: String(row.block_time || ""),
    txHash: String(row.tx_hash || ""),
    flow,
    asset,
    from,
    to,
    amount: amt,
    evidence,
    usd,
  };
}

async function apiFetch<T>(apiBase: string, apiKey: string, path: string): Promise<ApiEnvelope<T>> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${path} -> ${response.status} ${message.slice(0, 180)}`);
  }

  return response.json();
}

function compactValue(rawValue: string) {
  if (rawValue.startsWith("0x") && rawValue.length > 12) {
    return `${rawValue.slice(0, 6)}...${rawValue.slice(-4)}`;
  }
  return rawValue;
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

export async function fetchLiveNodeDetails(apiBase: string, apiKey: string, address: string): Promise<ExplorerNodeDetails> {
  const [historyResult, transfersResult, stablecoinsResult, statsResult, stablecoinCounterpartiesResult] = await Promise.allSettled([
    apiFetch<HistoryRow[]>(apiBase, apiKey, `/v1/eth/address/${address}/history?limit=250&days=30`),
    apiFetch<HistoryRow[]>(apiBase, apiKey, `/v1/eth/address/${address}/token-transfers?limit=250`),
    apiFetch<StablecoinPayload>(apiBase, apiKey, `/v1/eth/address/${address}/stablecoins`),
    apiFetch<StatsPayload>(apiBase, apiKey, `/v1/eth/address/${address}/stats`),
    apiFetch<StablecoinCounterpartyPayload>(apiBase, apiKey, `/v1/eth/address/${address}/stablecoin-counterparties?days=30&limit=8`),
  ]);

  const historyRows =
    historyResult.status === "fulfilled" && Array.isArray(historyResult.value.data)
      ? historyResult.value.data.map((row) => normalizeHistoryRow(address, row))
      : [];
  const transferRows =
    transfersResult.status === "fulfilled" && Array.isArray(transfersResult.value.data)
      ? transfersResult.value.data.map((row) => normalizeHistoryRow(address, row))
      : [];
  const deduped = new Map<string, ExplorerTransaction>();
  for (const row of [...historyRows, ...transferRows]) {
    deduped.set(`${row.txHash}:${row.date}:${row.asset}:${row.from}:${row.to}:${row.amount}`, row);
  }
  const history = Array.from(deduped.values()).sort((a, b) => Date.parse(b.date) - Date.parse(a.date));

  const stablecoins =
    stablecoinsResult.status === "fulfilled" ? stablecoinsResult.value.data?.stablecoin_balances ?? {} : {};

  const holdings = Object.entries(stablecoins).map(([symbol, payload]) => ({
    symbol,
    balance: toNumber(payload?.balance),
    usd: toNumber(payload?.balance),
  }));

  const stats = statsResult.status === "fulfilled" ? statsResult.value.data ?? {} : {};
  const totalStablecoinReceivedUsd = toNumber(stats.volume?.total_stablecoin_received_usd);
  const totalStablecoinSentUsd = toNumber(stats.volume?.total_stablecoin_sent_usd);

  const settledResults = [historyResult, transfersResult, stablecoinsResult, statsResult, stablecoinCounterpartiesResult];
  const successfulEnvelopes = settledResults
    .filter((result) => result.status === "fulfilled")
    .map((result) => (result as PromiseFulfilledResult<ApiEnvelope<unknown>>).value);
  const backendSource =
    successfulEnvelopes.find((entry) => entry.source && entry.source !== "cache")?.source ??
    successfulEnvelopes.find((entry) => entry.source)?.source ??
    "live";
  const warning =
    successfulEnvelopes.find((entry) => entry.warning)?.warning ??
    settledResults
      .filter((result) => result.status === "rejected")
      .map((result) => {
        const reason = (result as PromiseRejectedResult).reason;
        return reason instanceof Error ? reason.message : String(reason);
      })
      .find(Boolean);

  const hasAnyLiveData =
    history.length > 0 ||
    holdings.length > 0 ||
    Boolean(stats.transactions?.total) ||
    Boolean(stats.activity?.first_transaction) ||
    Boolean(stats.activity?.last_transaction);

  const derivedCounterparties = summarizeCounterparties(address, history);
  const stablecoinCounterparties =
    stablecoinCounterpartiesResult.status === "fulfilled"
      ? (stablecoinCounterpartiesResult.value.data?.counterparties ?? [])
          .map((row) => {
            const counterparty = String(row.counterparty || "");
            if (!counterparty) return null;
            const rawDirection = row.direction || "both";
            const direction =
              rawDirection === "inbound" ? "in" : rawDirection === "outbound" ? "out" : "mixed";
            return {
              address: counterparty,
              label: compactValue(counterparty),
              interactions: Math.max(1, Number(row.tx_count ?? 0)),
              direction,
            } satisfies CounterpartySummary;
          })
          .filter((row): row is CounterpartySummary => Boolean(row))
      : [];
  const counterparties = stablecoinCounterparties.length ? stablecoinCounterparties : derivedCounterparties;

  const historyEnvelope = historyResult.status === "fulfilled" ? historyResult.value : null;

  const hasAnyEnvelope = successfulEnvelopes.length > 0;
  if (!hasAnyLiveData && !hasAnyEnvelope) {
    throw new Error("No live node details were returned.");
  }

  return {
    address,
    dataSource: hasAnyLiveData ? "live" : "degraded",
    backendSource,
    warning,
    historyWindowDays: historyEnvelope?.window_days,
    historyMode: historyEnvelope?.history_mode,
    historyNote: historyEnvelope?.history_note,
    hotWallet: Boolean(historyEnvelope?.hot_wallet),
    hotWalletSource: historyEnvelope?.hot_wallet_source,
    hotWalletEntity: historyEnvelope?.hot_wallet_entity,
    hotWalletCategory: historyEnvelope?.hot_wallet_category,
    metrics: {
      inboundUsd: totalStablecoinReceivedUsd,
      outboundUsd: totalStablecoinSentUsd,
      netUsd: totalStablecoinReceivedUsd - totalStablecoinSentUsd,
      transactions: Number(stats.transactions?.total ?? history.length),
      firstActivity: String(stats.activity?.first_transaction || history.at(-1)?.date || ""),
      lastActivity: String(stats.activity?.last_transaction || history[0]?.date || ""),
    },
    holdings: holdings.length
      ? holdings
      : history
          .filter((row) => row.to.toLowerCase() === address.toLowerCase())
          .reduce<ExplorerNodeDetails["holdings"]>((acc, row) => {
            const existing = acc.find((entry) => entry.symbol === row.asset);
            if (existing) {
              existing.balance += row.amount;
              if (row.asset === "USDC") existing.usd += row.amount;
            } else {
              acc.push({
                symbol: row.asset,
                balance: row.amount,
                usd: row.asset === "USDC" ? row.amount : 0,
              });
            }
            return acc;
          }, []),
    transactions: history,
    counterparties,
  };
}
