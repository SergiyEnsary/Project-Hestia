import { useState } from "react";
import { getToken } from "./api/client";
import { ChatWindow } from "./components/ChatWindow";
import { MessageInput } from "./components/MessageInput";
import { SettingsModal } from "./components/SettingsModal";
import { useChat } from "./hooks/useChat";
import "./App.css";

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(!getToken());
  const { messages, loading, error, sendMessage } = useChat();

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Pythia</h1>
          <p className="subtitle">Oracle of Hestia</p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setSettingsOpen(true)}
        >
          Settings
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="main">
        <ChatWindow messages={messages} loading={loading} />
        <MessageInput onSend={sendMessage} disabled={loading} />
      </main>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
