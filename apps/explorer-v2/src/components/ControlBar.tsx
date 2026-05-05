type ControlBarProps = {
  apiKey: string;
  seedValue: string;
  graphState: string;
  artifactCount: number;
  onApiKeyChange: (value: string) => void;
  onLoad: () => void | Promise<void>;
  onClear: () => void;
  onAddressHistory: () => void;
  onHydrate: () => void;
};

export function ControlBar({
  apiKey,
  seedValue,
  graphState,
  artifactCount,
  onApiKeyChange,
  onLoad,
  onClear,
  onAddressHistory,
  onHydrate,
}: ControlBarProps) {
  return (
    <section className="toolbar">
      <div className="access">
        <label htmlFor="apiKeyInput">Scoped API key</label>
        <input
          id="apiKeyInput"
          type="password"
          value={apiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
          placeholder="biq_sk_live_..."
        />
        <button className="primary" type="button" onClick={onLoad}>Load</button>
        <button className="secondary" type="button" onClick={onClear}>Clear</button>
      </div>
      <div className="toolbar-actions">
        <button className="secondary" type="button" onClick={onAddressHistory}>Address History</button>
        <button className="secondary" type="button" onClick={onHydrate}>Hydrate</button>
      </div>
      <div className="toolbar-meta">
        <span><strong>Seed</strong> {seedValue}</span>
        <span><strong>Graph</strong> {graphState}</span>
        <span><strong>Artifacts</strong> {artifactCount}</span>
      </div>
    </section>
  );
}
