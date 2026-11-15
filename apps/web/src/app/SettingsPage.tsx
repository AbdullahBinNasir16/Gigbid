import { useEffect, useState } from "react";
import { api, type MemoryItem, type Settings } from "../lib/api/client";
import { ErrorNote, Loading, PageHead } from "../components/Layout";

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [style, setStyle] = useState<MemoryItem[]>([]);
  const [outcome, setOutcome] = useState<MemoryItem[]>([]);
  const [saved, setSaved] = useState<string | null>(null);
  const onboarding = new URLSearchParams(location.search).has("onboarding");

  async function loadMemory() {
    const a = await api.GET("/api/memory/{kind}", { params: { path: { kind: "style" } } });
    const b = await api.GET("/api/memory/{kind}", { params: { path: { kind: "outcome" } } });
    setStyle(a.data ?? []);
    setOutcome(b.data ?? []);
  }

  useEffect(() => {
    api.GET("/api/auth/me").then(({ data }) => data && setS(data.settings));
    loadMemory();
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!s) return;
    const { error } = await api.PUT("/api/auth/settings", { body: s });
    setSaved(error ? "Could not save." : "Saved.");
  }

  async function forget(kind: string, key: string) {
    await api.DELETE("/api/memory/{kind}/{key}", { params: { path: { kind, key } } });
    loadMemory();
  }

  if (!s) return <Loading what="Loading settings" />;
  return (
    <>
    <PageHead title="Settings" sub="Your portfolio, rates, budgets and what GigBid has learned." />
    <section className="grid">
      <form className="card form-grid" onSubmit={save} aria-label="Settings">
        <h2>{onboarding ? "Set up GigBid" : "Settings"}</h2>
        <label>Portfolio
          <select value={s.persona} onChange={(e) => setS({ ...s, persona: e.target.value as Settings["persona"] })}>
            <option value="ai_ml">AI/ML engineer persona</option>
            <option value="fullstack">Full-stack developer persona</option>
            <option value="data_analyst">Data analyst persona</option>
          </select>
        </label>
        <label>Marketplace
          <select value={s.marketplace} onChange={(e) => setS({ ...s, marketplace: e.target.value as Settings["marketplace"] })}>
            <option value="gigsim">GigSim (simulator)</option>
            <option value="upwork_live">Upwork (official MCP, OAuth)</option>
          </select>
        </label>
        <label>Hourly floor (USD)
          <input type="number" min={0} value={s.hourly_floor ?? ""} onChange={(e) => setS({ ...s, hourly_floor: e.target.value ? Number(e.target.value) : null })} />
        </label>
        <label>Weekly Connects budget
          <input type="number" min={0} value={s.weekly_connects_budget ?? 80} onChange={(e) => setS({ ...s, weekly_connects_budget: Number(e.target.value) })} />
        </label>
        <label>Saved searches (comma separated)
          <input value={(s.saved_searches ?? []).join(", ")} onChange={(e) => setS({ ...s, saved_searches: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
        </label>
        <label>Autonomy
          <select value={s.autonomy} onChange={(e) => setS({ ...s, autonomy: e.target.value as Settings["autonomy"] })}>
            <option value="suggest">Suggest only</option>
            <option value="auto_skip">Auto-skip very low fit (never auto-send)</option>
          </select>
        </label>
        <button type="submit" className="primary">Save</button>
        <ErrorNote error={saved} />
      </form>
      <div className="card">
        <h2>What GigBid has learned</h2>
        <h3>Style memory</h3>
        {style.length === 0 ? <p className="muted">Nothing yet. A pattern from your edits is kept only after it shows up in 3 different proposals.</p> : (
          <ul className="list">{style.map((m) => <li key={m.key}>{m.rule} <small className="muted">{m.promoted_by}</small> <button className="ghost" onClick={() => forget("style", m.key)} aria-label={`Delete ${m.rule}`}>Delete</button></li>)}</ul>
        )}
        <h3>Outcome memory</h3>
        {outcome.length === 0 ? <p className="muted">Nothing yet. Lessons need at least 10 outcomes in a category.</p> : (
          <ul className="list">{outcome.map((m) => <li key={m.key}>{m.rule} <button className="ghost" onClick={() => forget("outcome", m.key)}>Delete</button></li>)}</ul>
        )}
      </div>
    </section>
    </>
  );
}
