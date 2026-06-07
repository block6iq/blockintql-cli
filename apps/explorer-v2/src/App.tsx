import { useEffect, useMemo, useState } from "react";
import { ControlBar } from "./components/ControlBar";
import { GraphPanel } from "./components/GraphPanel";
import { NodeDrawer } from "./components/NodeDrawer";
import { OrchestratorPanel } from "./components/OrchestratorPanel";
import { PromptStudio } from "./components/PromptStudio";
import { Timeline } from "./components/Timeline";
import { TopBar } from "./components/TopBar";
import { shellSpecClassName, shellSpecSummary } from "./shellSpec";
import { useExplorerStore } from "./store";

export function App() {
  const [showPromptStudio, setShowPromptStudio] = useState(false);
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const {
    apiKey,
    workspaceName,
    workspaceGoal,
    graphState,
    artifactCount,
    nodes,
    edges,
    selectedNodeKey,
    nodeDetails,
    selectedTransactionKeys,
    steps,
    activeStepId,
    highlightedEdgeKeys,
    focusedTransactionKey,
    loadingNodeKey,
    setApiKey,
    loadWorkspace,
    clearWorkspace,
    runAddressHistory,
    hydrateGraph,
    saveView,
    toggleTransactionSelection,
    selectAllTransactions,
    clearTransactionSelection,
    plotSelectedTransactions,
    expandCounterparties,
    uploadSeeds,
    traceTransaction,
    shellPrompt,
    shellSpec,
    matchedShellRules,
    setSelectedNodeKey,
    focusStep,
    focusTransaction,
    openTransactionCounterparty,
    setShellPrompt,
    applyShellPrompt,
    exportEvidence,
    saveWorkspace,
    loadWorkspace: loadWsFromStore,
    getTimeline,
  } = useExplorerStore();

  // Expose for ControlBar buttons (standalone explorer-v2)
  (window as any).explorerSaveWorkspace = saveWorkspace;
  (window as any).explorerLoadWorkspace = (json: string) => loadWsFromStore(json);
  (window as any).explorerGetTimeline = getTimeline;

  const details = useMemo(() => nodeDetails[selectedNodeKey] || null, [nodeDetails, selectedNodeKey]);
  const selectedRows = selectedTransactionKeys[selectedNodeKey] ?? [];
  const activeStep = useMemo(() => steps.find((step) => step.id === activeStepId) ?? null, [steps, activeStepId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  return (
    <div className={`shell ${shellSpecClassName(shellSpec)}`}>
      <TopBar
        workspaceName={workspaceName}
        workspaceGoal={workspaceGoal}
        shellSummary={shellSpecSummary(shellSpec)}
        onSaveView={saveView}
        onCustomize={() => setShowPromptStudio(true)}
      />
      <ControlBar
        apiKey={apiKey}
        seedValue={nodes[0]?.rawValue ?? "Unknown"}
        graphState={graphState}
        artifactCount={artifactCount}
        onApiKeyChange={setApiKey}
        onLoad={loadWorkspace}
        onClear={clearWorkspace}
        onAddressHistory={runAddressHistory}
        onHydrate={hydrateGraph}
        onUploadSeeds={uploadSeeds}
      />

      <section className="workspace">
        <GraphPanel
          workspaceName={workspaceName}
          workspaceGoal={workspaceGoal}
          nodes={nodes}
          edges={edges}
          selectedNodeKey={selectedNodeKey}
          highlightedEdgeKeys={highlightedEdgeKeys}
          shellSpec={shellSpec}
          onSelectNode={setSelectedNodeKey}
        />
        <NodeDrawer
          nodeKey={selectedNodeKey}
          details={details}
          shellSpec={shellSpec}
          selectedRowKeys={selectedRows}
          focusedTransactionKey={focusedTransactionKey}
          activeStep={activeStep}
          isLoading={loadingNodeKey === selectedNodeKey}
          onFocusNode={setSelectedNodeKey}
          onExpandCounterparties={expandCounterparties}
          onFocusTransaction={focusTransaction}
          onTraceTransaction={traceTransaction}
          onOpenCounterparty={openTransactionCounterparty}
          onToggleRow={toggleTransactionSelection}
          onSelectAll={selectAllTransactions}
          onClearSelection={clearTransactionSelection}
          onPlotSelected={plotSelectedTransactions}
          onExportEvidence={exportEvidence}
        />
      </section>

      <OrchestratorPanel
        steps={steps}
        collapsed={timelineCollapsed}
        onToggleCollapse={() => setTimelineCollapsed((value) => !value)}
        onFocusStep={focusStep}
      />

      {/* Deeper explorer timeline UI (next wave) - standalone OSS value */}
      <Timeline events={getTimeline()} onFocusNode={setSelectedNodeKey} />

      {showPromptStudio ? (
        <PromptStudio
          prompt={shellPrompt}
          summary={shellSpecSummary(shellSpec)}
          matchedRules={matchedShellRules}
          onPromptChange={setShellPrompt}
          onApply={() => {
            applyShellPrompt();
            setShowPromptStudio(false);
          }}
          onClose={() => setShowPromptStudio(false)}
        />
      ) : null}
    </div>
  );
}
