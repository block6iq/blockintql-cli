import { useState } from "react";

type TopBarProps = {
  workspaceName: string;
  workspaceGoal: string;
  shellSummary: string;
  onSaveView: () => void;
  onCustomize: () => void;
};

export function TopBar({ workspaceName, workspaceGoal, shellSummary, onSaveView, onCustomize }: TopBarProps) {
  const [searchAddr, setSearchAddr] = useState("");

  const handleAddAddress = () => {
    const addr = searchAddr.trim();
    if (!addr) return;
    // Use global store exposure for adding seeds (real explorer search/add behavior)
    if ((window as any).explorerUploadSeeds) {
      (window as any).explorerUploadSeeds([addr]);
    } else if ((window as any).onUploadSeedsGlobal) {
      (window as any).onUploadSeedsGlobal([addr]);
    } else {
      // Fallback: alert or console for demo
      console.log("[Explorer] Add address (no global handler):", addr);
      alert(`Added ${addr} (in full integration this would call uploadSeeds and hydrate)`);
    }
    setSearchAddr("");
  };

  const handleExportGraph = () => {
    const exporter = (window as any).explorerExportGraph;
    if (exporter) {
      exporter();
    } else {
      // Fallback: try cytoscape if exposed
      console.log("[Explorer] Export requested - attach explorerExportGraph in GraphCanvas");
      alert("Graph export triggered (PNG/SVG). In live build this downloads the current Cytoscape view.");
    }
  };

  return (
    <header className="topbar explorer-header">
      <div className="command-card">
        <div className="mark">BIQ</div>
        <div>
          <div className="section-label">BLOCKCHAIN GRAPH EXPLORER</div>
          <h1>{workspaceName}</h1>
          <p>{workspaceGoal} — Real addresses • Search • Plot flows • Export</p>
        </div>
      </div>

      {/* Prominent search like real explorers (Etherscan/Blockscout style) */}
      <div className="top-search">
        <input
          type="text"
          placeholder="Search / paste address (0x...) and press Add or Enter"
          value={searchAddr}
          onChange={(e) => setSearchAddr(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleAddAddress(); }}
          className="explorer-search"
        />
        <button className="primary" onClick={handleAddAddress}>Add to Graph</button>
        <button className="secondary" onClick={handleExportGraph} title="Export current graph as PNG">Export PNG</button>
        <button className="secondary" onClick={() => {
          const svgExp = (window as any).explorerExportGraphSVG;
          if (svgExp) svgExp(); else alert("SVG export available in full Cytoscape setup");
        }}>Export SVG</button>
      </div>

      <div className="topbar-tools">
        <div className="tool-chip spec-chip" title="Shell spec from CLI (subtle now)">{shellSummary}</div>
        <button className="tool-chip button-chip" type="button" onClick={onSaveView}>Save Workspace</button>
        <button className="tool-chip button-chip" type="button" onClick={onCustomize}>
          Advanced Shell
        </button>
      </div>
    </header>
  );
}
