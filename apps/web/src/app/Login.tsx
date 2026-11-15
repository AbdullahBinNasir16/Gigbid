import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../lib/api/client";
import { ErrorNote } from "../components/Layout";
import { IconCheck, IconShield, IconSpark, Logo } from "../components/Icons";

function HeroArt() {
  return (
    <svg viewBox="0 0 360 230" className="hero-art" aria-hidden="true">
      <rect x="20" y="24" width="210" height="150" rx="16" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.25)" />
      <rect x="38" y="44" width="110" height="10" rx="5" fill="rgba(255,255,255,.85)" />
      <rect x="38" y="64" width="160" height="8" rx="4" fill="rgba(255,255,255,.35)" />
      <rect x="38" y="80" width="140" height="8" rx="4" fill="rgba(255,255,255,.35)" />
      <rect x="38" y="104" width="64" height="22" rx="11" fill="rgba(52,211,153,.9)" />
      <text x="70" y="119" textAnchor="middle" fontSize="11" fontWeight="700" fill="#053b2b">BID</text>
      <rect x="110" y="104" width="78" height="22" rx="11" fill="rgba(255,255,255,.18)" />
      <text x="149" y="119" textAnchor="middle" fontSize="11" fill="#fff">fit 82%</text>
      <rect x="38" y="140" width="120" height="8" rx="4" fill="rgba(255,255,255,.25)" />
      <rect x="160" y="96" width="180" height="112" rx="16" fill="#fff" />
      <circle cx="186" cy="122" r="12" fill="#eef2ff" />
      <path d="m180 122 4 4 8-8" stroke="#4f46e5" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <rect x="206" y="114" width="110" height="8" rx="4" fill="#c7d2fe" />
      <rect x="206" y="128" width="80" height="7" rx="3.5" fill="#e0e7ff" />
      <rect x="178" y="150" width="144" height="7" rx="3.5" fill="#e5e7eb" />
      <rect x="178" y="164" width="120" height="7" rx="3.5" fill="#e5e7eb" />
      <rect x="248" y="182" width="74" height="16" rx="8" fill="#4f46e5" />
      <text x="285" y="193.5" textAnchor="middle" fontSize="9" fontWeight="700" fill="#fff">APPROVE</text>
      <circle cx="318" cy="40" r="22" fill="rgba(255,255,255,.12)" />
      <circle cx="318" cy="40" r="9" fill="rgba(255,255,255,.35)" />
    </svg>
  );
}

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
    try {
      const res =
        mode === "login"
          ? await api.POST("/api/auth/login", { body: { username, password } })
          : await api.POST("/api/auth/signup", { body: { username, password, persona } });
      if (res.data) {
        setToken(res.data.token);
        nav(mode === "signup" ? "/settings?onboarding=1" : "/inbox");
      } else {
        setError(mode === "login" ? "Wrong username or password." : "Could not create the account (username taken?).");
      }
    } catch {
      setError("Can't reach the GigBid server right now. Please try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-hero" aria-hidden="true">
        <div className="brand light"><Logo size={34} /><span>GigBid</span></div>
        <h2>Bid on the right jobs, with proposals that prove it.</h2>
        <HeroArt />
        <ul className="hero-points">
          <li><IconSpark size={16} /> Finds and scores new jobs for you</li>
          <li><IconCheck size={16} /> Every claim backed by your portfolio</li>
          <li><IconShield size={16} /> Flags scams; nothing sent without you</li>
        </ul>
      </section>
      <section className="auth-panel">
        <form className="auth-form" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
          <div className="brand mobile-only"><Logo size={30} /><span>GigBid</span></div>
          <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="muted">
            {mode === "login" ? "Sign in to review today's jobs and drafts." : "Pick a starting portfolio. You can upload your own later."}
          </p>
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
              Starting persona
              <select name="persona" value={persona} onChange={(e) => setPersona(e.target.value as typeof persona)}>
                <option value="ai_ml">AI/ML engineer</option>
                <option value="fullstack">Full-stack web developer</option>
                <option value="data_analyst">Data analyst</option>
              </select>
            </label>
          )}
          <ErrorNote error={error} />
          <button type="submit" className="primary big" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
          <button type="button" className="link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}
