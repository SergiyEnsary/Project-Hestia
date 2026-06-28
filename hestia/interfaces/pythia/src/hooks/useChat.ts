import { useCallback, useRef, useState } from "react";
import { getToken, streamChat } from "../api/client";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const assistantBuffer = useRef("");

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;
    if (!getToken()) {
      setError("Set your API token in settings first.");
      return;
    }

    setError(null);
    setLoading(true);
    assistantBuffer.current = "";

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text.trim(),
    };
    setMessages((prev) => [...prev, userMsg]);

    const assistantId = crypto.randomUUID();
    let assistantAdded = false;

    await streamChat(text.trim(), (event) => {
      if (event.type === "error") {
        setError(event.message ?? "Unknown error");
        setLoading(false);
        return;
      }
      if (event.type === "token" && event.content) {
        assistantBuffer.current += event.content;
        if (!assistantAdded) {
          assistantAdded = true;
          setMessages((prev) => [
            ...prev,
            { id: assistantId, role: "assistant", content: assistantBuffer.current },
          ]);
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: assistantBuffer.current } : m
            )
          );
        }
      }
      if (event.type === "done") {
        setLoading(false);
      }
    });

    if (!assistantAdded) {
      setLoading(false);
    }
  }, [loading]);

  return { messages, loading, error, sendMessage, setError };
}
