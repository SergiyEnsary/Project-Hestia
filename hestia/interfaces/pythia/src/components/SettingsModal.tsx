import { FormEvent, useState } from "react";
import { getToken, setToken } from "../api/client";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [token, setTokenValue] = useState(getToken() ?? "");

  if (!open) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setToken(token.trim());
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Settings</h2>
        <p className="modal-hint">
          Enter your <code>HESTIA_API_TOKEN</code> from <code>.env</code>. Stored in
          sessionStorage only.
        </p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="token">API Token</label>
          <input
            id="token"
            type="password"
            value={token}
            onChange={(e) => setTokenValue(e.target.value)}
            placeholder="Paste token from .env"
            autoComplete="off"
          />
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
