import { useState } from "react";
import { SourceCard } from "./SourceCard";
import { Copy, RotateCcw, BookOpen, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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

  if (isUser) {
    return (
      <div className="message-row user" id={`msg-${message.message_id}`}>
        <div className="user-message-wrapper">
          <div className="user-message-bubble">
            {message.content}
          </div>
          <div className="msg-actions user-msg-actions">
            <button className="msg-action-btn" onClick={handleCopy} title="Copy">
              {copied ? <Check size={13} /> : <Copy size={13} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Assistant message — no bubble, modern flat style with markdown
  return (
    <div className="message-row assistant" id={`msg-${message.message_id}`}>
      <div className="assistant-message-wrapper">
        <div className="assistant-content">
          <div className="assistant-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const isBlock = match || String(children).includes("\n");
                  if (isBlock) {
                    return (
                      <div className="code-block-wrapper">
                        <div className="code-block-header">
                          <span className="code-block-lang">{match ? match[1] : "code"}</span>
                          <button
                            className="code-block-copy"
                            onClick={() => navigator.clipboard.writeText(String(children).replace(/\n$/, ""))}
                          >
                            <Copy size={12} /> Copy
                          </button>
                        </div>
                        <pre className="code-block"><code className={className} {...props}>{children}</code></pre>
                      </div>
                    );
                  }
                  return <code className="inline-code" {...props}>{children}</code>;
                },
                table({ children }) {
                  return <div className="md-table-wrapper"><table className="md-table">{children}</table></div>;
                },
                th({ children }) {
                  return <th className="md-th">{children}</th>;
                },
                td({ children }) {
                  return <td className="md-td">{children}</td>;
                },
                blockquote({ children }) {
                  return <blockquote className="md-blockquote">{children}</blockquote>;
                },
                ul({ children }) {
                  return <ul className="md-ul">{children}</ul>;
                },
                ol({ children }) {
                  return <ol className="md-ol">{children}</ol>;
                },
                li({ children }) {
                  return <li className="md-li">{children}</li>;
                },
                h1({ children }) { return <h1 className="md-h1">{children}</h1>; },
                h2({ children }) { return <h2 className="md-h2">{children}</h2>; },
                h3({ children }) { return <h3 className="md-h3">{children}</h3>; },
                p({ children }) { return <p className="md-p">{children}</p>; },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Action bar */}
          <div className="msg-actions assistant-actions">
            <button className="msg-action-btn" onClick={handleCopy} title="Copy">
              {copied ? <Check size={13} /> : <Copy size={13} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>

            {onRetry && (
              <button className="msg-action-btn" onClick={onRetry} title="Try again">
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

          {/* Sources (collapsible) */}
          {hasSources && showSources && (
            <div className="source-cards" style={{ marginTop: "var(--space-3)" }}>
              {message.sources.map((src, i) => (
                <SourceCard key={i} source={src} index={i} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <div className="assistant-message-wrapper">
        <div className="assistant-content">
          <div className="typing-indicator">
            <div className="typing-dot" />
            <div className="typing-dot" />
            <div className="typing-dot" />
          </div>
        </div>
      </div>
    </div>
  );
}
