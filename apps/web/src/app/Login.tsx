import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../lib/api/client";
import { ErrorNote } from "../components/Layout";

export default function Login() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [persona, setPersona] = useState<"ai_ml" | "fullstack" | "data_analyst">("ai_ml");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res =
      mode === "login"
        ? await api.POST("/api/auth/login", { body: { username, password } })
        : await api.POST("/api/auth/signup", { body: { username, password, persona } });
    setBusy(false);
    if (res.data) {
      setToken(res.data.token);
      nav(mode === "signup" ? "/settings?onboarding=1" : "/inbox");
    } else {
      setError(mode === "login" ? "Wrong username or password." : "Could not create the account (username taken?).");
    }
  }

  return (
    <div className="login">
      <form className="card narrow" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
        <h1>GigBid</h1>
        <p className="muted">Finds jobs, checks them, drafts grounded proposals. You approve everything before it is sent.</p>
        <label>
          Username
          <input name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={2} />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        </label>
        {mode === "signup" && (
          <label>
            Start with a persona (you can upload your own portfolio later)
            <select name="persona" value={persona} onChange={(e) => setPersona(e.target.value as typeof persona)}>
              <option value="ai_ml">AI/ML engineer</option>
              <option value="fullstack">Full-stack web developer</option>
              <option value="data_analyst">Data analyst</option>
            </select>
          </label>
        )}
        <ErrorNote error={error} />
        <button type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="ghost" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
