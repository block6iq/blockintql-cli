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
  onUploadSeeds: (addrs: string[]) => void;
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
  onUploadSeeds,
}: ControlBarProps & { onUploadSeeds: (addrs: string[]) => void }) {
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
        <label className="upload-label">
          Upload addresses (CSV/txt)
          <input
            type="file"
            accept=".txt,.csv,.json"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && onUploadSeeds) {
                const reader = new FileReader();
                reader.onload = () => {
                  const text = String(reader.result || "");
                  const addrs = text
                    .split(/[\s,\n\r]+/)
                    .map((s) => s.trim())
                    .filter((s) => /^0x[a-fA-F0-9]{40}$/.test(s));
                  if (addrs.length) onUploadSeeds(addrs);
                };
                reader.readAsText(file);
              }
              (e.target as HTMLInputElement).value = "";
            }}
          />
        </label>
        <button
          className="secondary"
          type="button"
          onClick={() => {
            const input = prompt("Paste comma or newline separated addresses:");
            if (input && onUploadSeeds) {
              const addrs = input
                .split(/[\s,\n\r]+/)
                .map((s) => s.trim())
                .filter((s) => /^0x[a-fA-F0-9]{40}$/.test(s));
              if (addrs.length) onUploadSeeds(addrs);
            }
          }}
        >
          Paste addresses
        </button>
        <button
          className="secondary"
          type="button"
          onClick={() => {
            // Trigger workspace save (portable JSON for standalone explorer-v2)
            if ((window as any).explorerSaveWorkspace) {
              (window as any).explorerSaveWorkspace();
            } else {
              alert("Workspace save available via store or CLI graph export");
            }
          }}
        >
          Save Workspace
        </button>
        <button
          className="secondary"
          type="button"
          onClick={() => {
            const tl = (window as any).explorerGetTimeline ? (window as any).explorerGetTimeline() : [];
            console.log("[Explorer] Timeline / attribution events:", tl);
            alert(`Timeline: ${tl.length} events logged to console (next wave: full UI view)`);
          }}
        >
          Show Timeline
        </button>
        <label className="upload-label">
          Load Workspace
          <input
            type="file"
            accept=".json"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                const reader = new FileReader();
                reader.onload = () => {
                  if ((window as any).explorerLoadWorkspace) {
                    (window as any).explorerLoadWorkspace(String(reader.result));
                  }
                };
                reader.readAsText(file);
              }
              (e.target as HTMLInputElement).value = "";
            }}
          />
        </label>
      </div>
      <div className="toolbar-meta">
        <span><strong>Seed</strong> {seedValue}</span>
        <span><strong>Graph</strong> {graphState}</span>
        <span><strong>Artifacts</strong> {artifactCount}</span>
      </div>
    </section>
  );
}
