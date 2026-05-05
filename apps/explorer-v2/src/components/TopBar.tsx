type TopBarProps = {
  workspaceName: string;
  workspaceGoal: string;
  shellSummary: string;
  onSaveView: () => void;
  onCustomize: () => void;
};

export function TopBar({ workspaceName, workspaceGoal, shellSummary, onSaveView, onCustomize }: TopBarProps) {
  return (
    <header className="topbar">
      <div className="command-card">
        <div className="mark">BI</div>
        <div>
          <div className="section-label">Graph Explorer //</div>
          <h1>{workspaceName}</h1>
          <p>{workspaceGoal}</p>
        </div>
      </div>
      <div className="topbar-tools">
        <div className="tool-chip spec-chip">{shellSummary}</div>
        <button className="tool-chip button-chip" type="button" onClick={onSaveView}>Save View</button>
        <button className="tool-chip button-chip" type="button" onClick={onCustomize}>
          Customize Shell
        </button>
      </div>
    </header>
  );
}
