import type { OrchestrationStep } from "../types";

type OrchestratorPanelProps = {
  steps: OrchestrationStep[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onFocusStep: (stepId: string) => void;
};

function formatCost(step: OrchestrationStep) {
  if (step.credits === 0 && step.usd === 0) return "local / no charge";
  return `${step.credits} cr · $${step.usd.toFixed(2)}`;
}

export function OrchestratorPanel({ steps, collapsed, onToggleCollapse, onFocusStep }: OrchestratorPanelProps) {
  return (
    <section className="orchestrator">
      <div className="orchestrator-head">
        <div>
          <div className="section-label">Investigation Run</div>
          <h2 className="orchestrator-title">Agent Timeline</h2>
          <p className="orchestrator-subtitle">See what the investigation agent is doing, what it used, and what it cost.</p>
        </div>
        <button className="secondary" type="button" onClick={onToggleCollapse}>
          {collapsed ? "Expand Timeline" : "Collapse Timeline"}
        </button>
      </div>

      {!collapsed ? <div className="orchestrator-list">
        {steps.map((step, index) => (
          <article
            className={`step-card step-${step.status} ${step.focusNodeKey ? "step-clickable" : ""}`}
            key={step.id}
            onClick={() => step.focusNodeKey ? onFocusStep(step.id) : undefined}
          >
            <div className="step-index">{index + 1}</div>
            <div className="step-body">
              <div className="step-topline">
                <strong>{step.label}</strong>
                <span className={`step-status step-status-${step.status}`}>{step.status}</span>
              </div>
              <p className="step-detail">{step.detail}</p>
              <div className="step-meta">
                <span className="chain-pill">{step.source}</span>
                <span className="chain-pill">{formatCost(step)}</span>
              </div>
            </div>
          </article>
        ))}
      </div> : null}
    </section>
  );
}
