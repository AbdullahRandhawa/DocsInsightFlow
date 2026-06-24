export function UploadSettings({ chunkSize, onChunkSizeChange }) {
  return (
    <div className="upload-settings">
      <span className="upload-settings-label">⚙ Processing</span>
      <div className="slider-group">
        <span className="slider-label">Chunk Size</span>
        <input
          id="chunk-size-slider"
          type="range"
          min={100}
          max={1000}
          step={50}
          value={chunkSize}
          onChange={(e) => onChunkSizeChange(Number(e.target.value))}
        />
        <span className="slider-value">{chunkSize}</span>
        <span className="slider-label" style={{ color: "var(--color-text-muted)" }}>words</span>
      </div>
    </div>
  );
}
