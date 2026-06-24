import { FileText, AlertCircle } from "lucide-react";

function ScoreBadge({ score }) {
  const pct = Math.round(score * 100);
  const level = score >= 0.8 ? "high" : score >= 0.6 ? "medium" : "low";
  return <span className={`score-badge ${level}`}>{pct}%</span>;
}

export function SourceCard({ source, index }) {
  return (
    <div className="source-card" id={`source-card-${index}`}>
      <div className="source-card-header">
        <div className="source-card-file">
          <FileText size={12} />
          <span className="source-card-file-name">{source.file_name}</span>
        </div>
        <div className="source-card-meta">
          <span className="source-card-page">p.{source.page}</span>
          <ScoreBadge score={source.score} />
        </div>
      </div>
      <p className="source-card-excerpt">"{source.excerpt}"</p>
    </div>
  );
}
