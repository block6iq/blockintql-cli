import type { ShellSpec } from "../shellSpec";
import type { ExplorerNodeDetails, ExplorerTransaction, OrchestrationStep } from "../types";

type NodeDrawerProps = {
  nodeKey: string;
  details: ExplorerNodeDetails | null;
  shellSpec: ShellSpec;
  selectedRowKeys: string[];
  focusedTransactionKey: string | null;
  activeStep: OrchestrationStep | null;
  isLoading: boolean;
  onFocusNode: (nodeKey: string) => void | Promise<void>;
  onExpandCounterparties: (nodeKey: string) => void;
  onFocusTransaction: (nodeKey: string, txKey: string) => void;
  onTraceTransaction: (nodeKey: string, txKey: string) => void | Promise<void>;
  onOpenCounterparty: (nodeKey: string, txKey: string, side: "from" | "to") => void | Promise<void>;
  onToggleRow: (nodeKey: string, txKey: string) => void;
  onSelectAll: (nodeKey: string) => void;
  onClearSelection: (nodeKey: string) => void;
  onPlotSelected: (nodeKey: string) => void;
  onExportEvidence?: (nodeKey: string) => void;
};

function transactionKey(row: ExplorerTransaction) {
  return `${row.txHash}:${row.date}`;
}

function formatUsd(value: number) {
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatCompactUsd(value: number) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(value: string) {
  if (!value) return "Unknown";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

function formatAddress(value: string) {
  if (value.startsWith("0x") && value.length > 12) {
    return `${value.slice(0, 6)}...${value.slice(-4)}`;
  }
  return value;
}

function dataSourceLabel(source: ExplorerNodeDetails["dataSource"]) {
  switch (source) {
    case "mock":
      return "mock seed data";
    case "derived":
      return "derived from plotted evidence";
    case "live":
      return "live indexed data";
    case "fallback":
      return "provider fallback";
    case "degraded":
      return "live degraded response";
    default:
      return source;
  }
}

function hotWalletLabel(details: ExplorerNodeDetails) {
  if (!details.hotWallet) return null;
  if (details.hotWalletCategory) {
    return `${details.hotWalletCategory} hot wallet`;
  }
  return "service wallet";
}

export function NodeDrawer({
  nodeKey,
  details,
  shellSpec,
  selectedRowKeys,
  focusedTransactionKey,
  activeStep,
  isLoading,
  onFocusNode,
  onExpandCounterparties,
  onFocusTransaction,
  onTraceTransaction,
  onOpenCounterparty,
  onToggleRow,
  onSelectAll,
  onClearSelection,
  onPlotSelected,
}: NodeDrawerProps) {
  const isThreatMode = shellSpec.investigationMode === "threat";
  if (!details) {
    return (
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="section-label">{isThreatMode ? "Threat Intel Console" : "Analyst Drawer"}</div>
            <h2 className="drawer-title">{isThreatMode ? "Threat Intel Console" : "Node Transactions"}</h2>
            <p className="drawer-subtitle">
              {isThreatMode
                ? "Open a graph node to review flagged signals, labeled flows, and threat-linked counterparties."
                : "Select a graph node to open the transaction drawer and review evidence."}
            </p>
          </div>
        </div>
        <div className="drawer-body">
          <div className="empty">No node selected yet.</div>
        </div>
      </aside>
    );
  }

  const selectedCount = selectedRowKeys.length;
  const labeledCount = details.transactions.filter((row) => row.evidence === "labeled").length;
  const threatHits = labeledCount + (details.counterparties?.filter((counterparty) => counterparty.label !== formatAddress(counterparty.address)).length ?? 0);
  const hasThreatBanner = threatHits > 0 || isThreatMode;
  const headerTitle = isThreatMode ? "Threat Intel Console" : "Node Transactions";
  const headerSection = isThreatMode ? "Threat Intel" : "Node Transactions";
  const threatCounterparties =
    details.counterparties?.filter((counterparty) => counterparty.label !== formatAddress(counterparty.address)) ?? [];
  const visibleCounterparties = isThreatMode && threatCounterparties.length ? threatCounterparties : details.counterparties ?? [];
  const serviceWalletLabel = hotWalletLabel(details);
  const hasServiceWalletTriage = Boolean(details.hotWallet && (details.historyNote || details.metrics.transactions || visibleCounterparties.length));

  return (
    <aside className="drawer">
      <div className="drawer-head">
        <div className="drawer-heading">
          <div className="section-label">{headerSection}</div>
          <h2 className="drawer-title">{headerTitle}</h2>
          <div className="drawer-subtitle-row">
            <span className="address-line address-line-head">{details.address}</span>
            <span className="drawer-subtitle">
              Ethereum · {details.metrics.transactions} transactions
              {details.historyWindowDays ? ` · ${details.historyWindowDays}d view` : ""}
              {serviceWalletLabel ? ` · ${serviceWalletLabel}` : ""}
              {isThreatMode ? " · signal-priority review" : ""}
            </span>
          </div>
          <div className="drawer-badges">
            <span className="chain-pill">Ethereum</span>
            <span className="chain-pill">{details.metrics.transactions} matches</span>
            <span className="chain-pill">{labeledCount} labeled</span>
            <span className="chain-pill">2 related investigations</span>
            {details.hotWallet ? <span className="chain-pill">Hot wallet</span> : null}
            {details.hotWalletEntity ? <span className="chain-pill">{details.hotWalletEntity}</span> : null}
            {details.hotWalletSource ? <span className="chain-pill">{details.hotWalletSource}</span> : null}
            {isThreatMode ? <span className="chain-pill threat-mode-pill">Threat mode</span> : null}
          </div>
          <div className="result-context result-context-head">
            <span className="chain-pill">{dataSourceLabel(details.dataSource)}</span>
            {details.backendSource ? <span className="chain-pill">{details.backendSource}</span> : null}
            {activeStep ? (
              <>
                <span className="chain-pill">{activeStep.source}</span>
                <span className="chain-pill">
                  {activeStep.credits === 0 && activeStep.usd === 0
                    ? "local / no charge"
                    : `${activeStep.credits} cr · $${activeStep.usd.toFixed(2)}`}
                </span>
                <span className={`step-status step-status-${activeStep.status}`}>{activeStep.status}</span>
              </>
            ) : null}
          </div>
        </div>
        <div className="drawer-actions">
          <button className="secondary" type="button" onClick={() => onFocusNode(nodeKey)}>Focus Node</button>
          <button className="secondary" type="button" onClick={() => onExpandCounterparties(nodeKey)}>Expand Counterparties</button>
          {onExportEvidence && (
            <button className="primary" type="button" onClick={() => onExportEvidence(nodeKey)}>
              Export Evidence Bundle (deterministic)
            </button>
          )}
        </div>
      </div>
      <div className="drawer-body">
        {hasThreatBanner ? (
          <div className={`threat-banner ${isThreatMode ? "threat-banner-mode" : ""}`}>
            <div>
              <div className="section-label threat-banner-label">Threat Intelligence Hit</div>
              <strong>
                {threatHits > 0
                  ? `${threatHits} investigation signal${threatHits === 1 ? "" : "s"} surfaced for this node.`
                  : "Threat intel mode is active for this node."}
              </strong>
              <span>
                {threatHits > 0
                  ? "Expand counterparties and review labeled transfers in the evidence table."
                  : "Labeled rows, suspicious counterparties, and flagged flow styling are prioritized in this view."}
              </span>
            </div>
            <span className="threat-banner-count">{threatHits}</span>
          </div>
        ) : null}

        {activeStep ? <div className="result-context-detail">{activeStep.label}</div> : null}

        {hasServiceWalletTriage ? (
          <div className="threat-banner">
            <div>
              <div className="section-label threat-banner-label">Service-Wallet Triage</div>
              <strong>
                {details.hotWalletEntity
                  ? `${details.hotWalletEntity} is being reviewed as a high-throughput service wallet.`
                  : "This node is being reviewed as a high-throughput service wallet."}
              </strong>
              <span>
                {details.historyNote ||
                  "The drawer is prioritizing summary evidence and counterparties over a full ledger dump for this address."}
              </span>
            </div>
            <span className="threat-banner-count">{details.historyWindowDays ? `${details.historyWindowDays}d` : "hot"}</span>
          </div>
        ) : null}

        {details.dataSource !== "live" ? (
          <div className="drawer-note">
            {details.dataSource === "mock"
              ? "This open-source explorer is currently seeded with mock data."
              : details.dataSource === "degraded"
                ? details.warning || "The live endpoint responded in degraded mode, so this drawer is showing an honest empty-state response instead of pretending live evidence loaded."
              : "This node view was derived from evidence already loaded into the shell, not from a fresh API fetch."}
          </div>
        ) : null}

        {details.warning && details.dataSource === "live" ? <div className="drawer-note">{details.warning}</div> : null}

        {isLoading ? <div className="drawer-note">Loading live indexed history, balances, and stats for this node...</div> : null}

        {visibleCounterparties.length ? (
          <div className="counterparty-strip">
            <div className="section-label">{isThreatMode ? "Flagged Counterparties" : "Top Counterparties"}</div>
            <div className="counterparty-chip-row">
              {visibleCounterparties.map((counterparty) => (
                <button
                  key={counterparty.address}
                  className="counterparty-chip"
                  type="button"
                  onClick={() => onFocusNode(`node:${counterparty.address.toLowerCase()}`)}
                >
                  {counterparty.label} · {counterparty.interactions}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="metrics">
          <div className="metric inbound">
            <label>Inbound</label>
            <strong>{formatCompactUsd(details.metrics.inboundUsd)}</strong>
            <span>{details.transactions.filter((row) => row.flow === "in").length} deposits</span>
          </div>
          <div className="metric outbound">
            <label>Outbound</label>
            <strong>{formatCompactUsd(details.metrics.outboundUsd)}</strong>
            <span>{details.transactions.filter((row) => row.flow === "out").length} withdrawals</span>
          </div>
          <div className="metric net">
            <label>Net Flow</label>
            <strong>{formatCompactUsd(details.metrics.netUsd)}</strong>
            <span>{details.metrics.netUsd >= 0 ? "Net receiver" : "Net sender"}</span>
          </div>
        </div>

        {details.hotWallet ? (
          <div className="drawer-note">
            {details.hotWalletEntity
              ? `${details.hotWalletEntity} is active enough that BlockINTQL favors condensed history, wallet stats, and counterparty evidence in the explorer.`
              : "This address is active enough that BlockINTQL favors condensed history, wallet stats, and counterparty evidence in the explorer."}
          </div>
        ) : null}

        <div className="case-intel-grid">
          <div className="case-intel-card">
            <label>First Activity</label>
            <strong>{formatDate(details.metrics.firstActivity)}</strong>
          </div>
          <div className="case-intel-card">
            <label>Last Activity</label>
            <strong>{formatDate(details.metrics.lastActivity)}</strong>
          </div>
          <div className="case-intel-card">
            <label>Total Balance</label>
            <strong>{formatUsd(details.holdings.reduce((sum, holding) => sum + holding.usd, 0))}</strong>
          </div>
          <div className="case-intel-card">
            <label>Threat Signals</label>
            <strong>{threatHits}</strong>
          </div>
        </div>

        <div className="table-controls">
          <div className="filter-row">
            <span className={`filter-chip ${isThreatMode ? "" : "active"}`}>All</span>
            <span className="filter-chip">Deposits</span>
            <span className="filter-chip">Withdrawals</span>
            <span className={`filter-chip ${isThreatMode ? "active" : ""}`}>Labeled</span>
            <span className="filter-chip">Live</span>
          </div>
          <div className="table-toolbar">
            <span className="status-line">
              {selectedCount} selected · {isThreatMode ? "labeled and suspicious evidence prioritized" : "local plotting only"}
            </span>
            <span className="chain-pill">Token: All</span>
            <span className="chain-pill">Min $: 0</span>
          </div>
        </div>

        <div className="selection-actions">
          <div className="selection-actions-inline">
            <button className="secondary" type="button" onClick={() => onSelectAll(nodeKey)}>
              Select All
            </button>
            <button className="secondary" type="button" onClick={() => onClearSelection(nodeKey)}>
              Clear Selection
            </button>
          </div>
          <button
            className="primary plot-bar-button"
            type="button"
            onClick={() => onPlotSelected(nodeKey)}
            disabled={selectedCount === 0}
          >
            Plot Selected {selectedCount ? `(${selectedCount})` : ""}
          </button>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th></th>
                <th>Date</th>
                <th>Tx Hash</th>
                <th>Trace</th>
                <th>Flow</th>
                <th>Risk</th>
                <th>Asset</th>
                <th>From</th>
                <th>To</th>
                <th>USD</th>
                <th>Amount</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {details.transactions.map((row) => {
                const rowKey = transactionKey(row);
                const isSelected = selectedRowKeys.includes(rowKey);
                const isFocused = focusedTransactionKey === rowKey;
                return (
                <tr
                  key={row.txHash + row.date}
                  className={`${isSelected ? "is-selected" : ""} ${isFocused ? "is-focused" : ""}`.trim()}
                  onClick={() => onFocusTransaction(nodeKey, rowKey)}
                >
                  <td>
                    <input
                      className="row-check"
                      type="checkbox"
                      checked={isSelected}
                      onChange={(event) => {
                        event.stopPropagation();
                        onToggleRow(nodeKey, rowKey);
                      }}
                    />
                  </td>
                  <td>{formatDate(row.date)}</td>
                  <td className="tx-hash">{row.txHash.slice(0, 10)}...</td>
                  <td>
                    <button
                      className="trace-button"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onTraceTransaction(nodeKey, rowKey);
                      }}
                    >
                      Trace
                    </button>
                  </td>
                  <td>
                    <span className={`flow-pill ${row.flow}`}>{row.flow.toUpperCase()}</span>
                  </td>
                  <td><span className={`risk-pill ${row.evidence}`}>{row.evidence}</span></td>
                  <td>{row.asset}</td>
                  <td>
                    <button className="address-button" type="button" onClick={(event) => {
                      event.stopPropagation();
                      onOpenCounterparty(nodeKey, rowKey, "from");
                    }}>
                      {formatAddress(row.from)}
                    </button>
                  </td>
                  <td>
                    <button className="address-button" type="button" onClick={(event) => {
                      event.stopPropagation();
                      onOpenCounterparty(nodeKey, rowKey, "to");
                    }}>
                      {formatAddress(row.to)}
                    </button>
                  </td>
                  <td>{row.asset === "USDC" ? formatUsd(row.amount) : "—"}</td>
                  <td>{row.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td>{row.evidence}</td>
                </tr>
              )})}
            </tbody>
          </table>
        </div>

        <div className="summary-grid">
          <div className="meta-card summary-card">
            <label>Total Transactions</label>
            <strong>{details.metrics.transactions}</strong>
          </div>
          <div className="meta-card summary-card">
            <label>First Activity</label>
            <strong>{formatDate(details.metrics.firstActivity)}</strong>
          </div>
          <div className="meta-card summary-card">
            <label>Last Activity</label>
            <strong>{formatDate(details.metrics.lastActivity)}</strong>
          </div>
          <div className="meta-card summary-card">
            <label>Total Balance</label>
            <strong>{formatUsd(details.holdings.reduce((sum, holding) => sum + holding.usd, 0))}</strong>
          </div>
        </div>

        <div className="holdings">
          <div className="holdings-head">
            <div className="section-label">Wallet Summary</div>
            <span className="status-line">Token holdings</span>
          </div>
          <div className="holdings-grid">
            {details.holdings.map((holding) => (
              <div className="holding-row" key={holding.symbol}>
                <strong>{holding.symbol}</strong>
                <div>
                  {holding.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} · {formatUsd(holding.usd)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
