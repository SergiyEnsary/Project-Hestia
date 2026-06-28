import { useEffect, useRef } from "react";
import type { Message } from "../hooks/useChat";

interface ChatWindowProps {
  messages: Message[];
  loading: boolean;
}

export function ChatWindow({ messages, loading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <h2>Consult Hestia</h2>
          <p>Ask about the weather, your day, or anything Hestia can help with.</p>
        </div>
      )}
      {messages.map((msg) => (
        <div key={msg.id} className={`message message-${msg.role}`}>
          <span className="message-role">{msg.role === "user" ? "You" : "Hestia"}</span>
          <div className="message-content">{msg.content}</div>
        </div>
      ))}
      {loading && (
        <div className="message message-assistant">
          <span className="message-role">Hestia</span>
          <div className="message-content typing">Thinking…</div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
