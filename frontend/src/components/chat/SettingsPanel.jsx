export function SettingsPanel({ topK, threshold, onTopKChange, onThresholdChange }) {
  return (
    <div className="settings-panel" id="settings-panel">
      <div className="settings-group">
        <span className="settings-group-label">🔍 Top-K</span>
        <div className="slider-group">
          <input
            id="topk-slider"
            type="range"
            min={1}
            max={10}
            step={1}
            value={topK}
            onChange={(e) => onTopKChange(Number(e.target.value))}
            style={{ width: 100 }}
          />
          <span className="slider-value">{topK}</span>
        </div>
      </div>

      <div className="settings-group">
        <span className="settings-group-label">🎯 Threshold</span>
        <div className="slider-group">
          <input
            id="threshold-slider"
            type="range"
            min={0.1}
            max={0.95}
            step={0.05}
            value={threshold}
            onChange={(e) => onThresholdChange(Number(e.target.value))}
            style={{ width: 100 }}
          />
          <span className="slider-value">{threshold.toFixed(2)}</span>
        </div>
      </div>

      <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
        Retrieval settings
      </span>
    </div>
  );
}
