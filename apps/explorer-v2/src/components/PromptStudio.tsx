import { shellSpecSummary } from "../shellSpec";

type PromptStudioProps = {
  prompt: string;
  summary: string;
  matchedRules: string[];
  onPromptChange: (value: string) => void;
  onApply: () => void;
  onClose: () => void;
};

export function PromptStudio({
  prompt,
  summary,
  matchedRules,
  onPromptChange,
  onApply,
  onClose,
}: PromptStudioProps) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="prompt-studio-modal" onClick={(event) => event.stopPropagation()}>
        <div className="prompt-copy">
          <div className="section-label">Shell Builder</div>
          <h2>Shape the shell with a deterministic prompt.</h2>
          <p>
            Let users describe the workstation they want, then compile that prompt into a safe shell
            spec instead of arbitrary UI generation.
          </p>
          <div className="prompt-example-list">
            <div className="status-line">Try prompts like</div>
            <div className="prompt-example-chip">Build me a shell for following the money</div>
            <div className="prompt-example-chip">I want to triage wallets fast</div>
            <div className="prompt-example-chip">Make this feel briefing-ready for a client meeting</div>
            <div className="prompt-example-chip">Build a case board for tracing counterparties</div>
            <div className="prompt-example-chip">Move transaction drawer to left side</div>
            <div className="prompt-example-chip">Move drawer to bottom</div>
            <div className="prompt-example-chip">Angle nodes to the right on withdrawals</div>
            <div className="prompt-example-chip">Make this a threat intel explorer</div>
            <div className="prompt-example-chip">Prioritize suspicious counterparties</div>
          </div>
        </div>
        <button className="modal-close" type="button" onClick={onClose}>
          Close
        </button>

        <div className="prompt-form">
          <textarea
            className="prompt-input"
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            placeholder="Example: Build a case board for tracing counterparties and move the transaction drawer to the left side."
          />
          <div className="prompt-actions">
            <div className="prompt-summary">
              <span className="status-line">Active shell spec</span>
              <strong>{summary}</strong>
              {matchedRules.length > 0 ? (
                <div className="prompt-rule-row">
                  {matchedRules.map((rule) => (
                    <span className="filter-chip" key={rule}>
                      {rule}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="status-line">Using default analyst workstation preset.</div>
              )}
            </div>
            <button className="primary" type="button" onClick={onApply}>
              Apply Shell Prompt
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
