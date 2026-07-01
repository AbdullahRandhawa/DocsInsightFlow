import { useEffect, useRef } from "react";
import { MessageBubble, TypingIndicator, StreamingBubble } from "./MessageBubble";
import { FileText, Search, UploadCloud, Zap, Layers } from "lucide-react";

export function ChatWindow({ messages, isLoading, streamingState, hasDocuments, onRetry, onSend, onUploadClick }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, streamingState]);

  if (messages.length === 0 && !streamingState) {
    return (
      <div className="chat-window empty-state-container">
        <div className="empty-state-content">
          <div className="empty-state-header">
            <h2 className="empty-state-title">
              Welcome to <span style={{
                background: "var(--gradient-accent)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text"
              }}>DocsInsightFlow</span>
            </h2>
            <p className="empty-state-subtitle">
              Upload your documents and start chatting instantly. Our AI analyzes your PDFs, TXTs, and DOCXs to find answers, summarize data, and extract key insights seamlessly.
            </p>
          </div>

          <div className="empty-state-features">
            <div className="feature-pill">
              <div className="feature-icon"><FileText size={18} /></div>
              <div className="feature-text">
                <strong>Contextual Analysis</strong>
                <span>AI understands the full context of your documents for highly accurate answers</span>
              </div>
            </div>
            <div className="feature-pill">
              <div className="feature-icon"><Search size={18} /></div>
              <div className="feature-text">
                <strong>Semantic Search</strong>
                <span>Find exactly what you need using natural language—no exact keyword matches required</span>
              </div>
            </div>
            <div className="feature-pill">
              <div className="feature-icon"><Zap size={18} /></div>
              <div className="feature-text">
                <strong>Instant Summarization</strong>
                <span>Condense lengthy reports and large documents into digestible key takeaways in seconds</span>
              </div>
            </div>
            <div className="feature-pill">
              <div className="feature-icon"><Layers size={18} /></div>
              <div className="feature-text">
                <strong>Multi-Doc Intelligence</strong>
                <span>Upload multiple files at once and cross-reference data seamlessly across all of them</span>
              </div>
            </div>
          </div>

          <div className="empty-state-actions">
            <button className="upload-pill" onClick={onUploadClick}>
              <div className="upload-pill-icon"><UploadCloud size={20} /></div>
              <div className="upload-pill-text">
                <strong>Upload Document</strong>
                <span>Support for PDF, TXT, and DOCX formats</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-window" id="chat-window">
      {messages.map((msg, i) => (
        <MessageBubble
          key={msg.message_id}
          message={msg}
          onRetry={msg.role === "assistant" && onRetry ? () => onRetry(i) : null}
        />
      ))}
      {isLoading && !streamingState && <TypingIndicator />}
      {streamingState && (
        <StreamingBubble
          status={streamingState.status}
          content={streamingState.content}
        />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
