import { useState } from "react";
import { SourceCard } from "./SourceCard";
import { AlertTriangle, Copy, RotateCcw, BookOpen, Check } from "lucide-react";

export function MessageBubble({ message, onRetry }) {
  const isUser = message.role === "user";
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasSources = !isUser && message.sources && message.sources.length > 0;

  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`} id={`msg-${message.message_id}`}>
      <div style={{ display: "flex", flexDirection: "column", maxWidth: isUser ? "72%" : "100%" }}>
        <div className={`message-bubble ${isUser ? "user" : "assistant"}`}>
          {message.content.split("\n").map((line, i) =>
            line ? <p key={i}>{line}</p> : <br key={i} />
          )}
        </div>

        {/* No context banner */}
        {!isUser && message.has_context === false && (
          <div className="no-context-banner">
            <AlertTriangle size={12} />
            No relevant context found in documents for this query
          </div>
        )}

        {/* Action bar — only for assistant messages */}
        {!isUser && (
          <div className="msg-actions">
            <button
              className="msg-action-btn"
              onClick={handleCopy}
              title="Copy"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>

            {onRetry && (
              <button
                className="msg-action-btn"
                onClick={onRetry}
                title="Try again"
              >
                <RotateCcw size={13} />
                <span>Try again</span>
              </button>
            )}

            {hasSources && (
              <button
                className={`msg-action-btn ${showSources ? "active" : ""}`}
                onClick={() => setShowSources(!showSources)}
                title="Sources"
              >
                <BookOpen size={13} />
                <span>Sources ({message.sources.length})</span>
              </button>
            )}
          </div>
        )}

        {/* Sources (collapsible) */}
        {hasSources && showSources && (
          <div className="source-cards" style={{ marginTop: "var(--space-2)" }}>
            {message.sources.map((src, i) => (
              <SourceCard key={i} source={src} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <div className="message-bubble assistant" style={{ padding: "var(--space-3) var(--space-4)" }}>
        <div className="typing-indicator">
          <div className="typing-dot" />
          <div className="typing-dot" />
          <div className="typing-dot" />
        </div>
      </div>
    </div>
  );
}
