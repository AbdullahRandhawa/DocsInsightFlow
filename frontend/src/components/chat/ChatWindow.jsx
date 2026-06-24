import { useEffect, useRef } from "react";
import { MessageBubble, TypingIndicator } from "./MessageBubble";
import { FileText } from "lucide-react";

export function ChatWindow({ messages, isLoading, hasDocuments, onRetry }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  if (messages.length === 0) {
    return (
      <div className="chat-window">
        <div className="empty-state">
          <div className="empty-state-icon">
            <FileText size={40} strokeWidth={1.5} />
          </div>
          <h3 className="empty-state-title">
            {hasDocuments ? "Ready to answer" : "No documents yet"}
          </h3>
          <p className="empty-state-text">
            {hasDocuments
              ? "Ask anything about your uploaded documents."
              : "Click the paperclip in the input bar to upload a PDF, TXT, or DOCX."}
          </p>
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
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
