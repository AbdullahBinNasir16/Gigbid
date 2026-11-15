import { useEffect, useState } from "react";
import { api } from "../lib/api/client";
import { Empty, Loading, PageHead, Stat } from "../components/Layout";
import { IconBolt, IconChart, IconCheck, IconCoins } from "../components/Icons";
import { Donut } from "../components/Charts";

/** Horizontal stacked bar per category: bid / watch / skip. */
function CategoryBars({ rows }: { rows: [string, Record<string, number>][] }) {
  const max = Math.max(1, ...rows.map(([, v]) => (v.bid ?? 0) + (v.watch ?? 0) + (v.skip ?? 0)));
  return (
    <div className="bars">
      {rows.map(([c, v]) => {
        const parts: [string, number, string][] = [["bid", v.bid ?? 0, "var(--ok)"], ["watch", v.watch ?? 0, "var(--warn)"], ["skip", v.skip ?? 0, "var(--muted-2)"]];
        const total = parts.reduce((n, p) => n + p[1], 0);
        return (
          <div key={c} className="bar-row">
            <span className="bar-label">{c.replace(/_/g, " ")}</span>
            <div className="bar-track" style={{ width: `${(total / max) * 100}%` }} role="img"
              aria-label={`${c}: ${v.bid ?? 0} bid, ${v.watch ?? 0} watch, ${v.skip ?? 0} skip`}>
              {parts.map(([k, n, color]) => n > 0 && <span key={k} style={{ flex: n, background: color }} title={`${k}: ${n}`} />)}
            </div>
            <span className="muted small">{total}</span>
          </div>
        );
      })}
      <div className="legend small muted">
        <span><i style={{ background: "var(--ok)" }} /> bid</span>
        <span><i style={{ background: "var(--warn)" }} /> watch</span>
        <span><i style={{ background: "var(--muted-2)" }} /> skip</span>
      </div>
    </div>
  );
}

export default function Analytics() {
  const [a, setA] = useState<any>(null);
  useEffect(() => {
    api.GET("/api/analytics").then(({ data }) => setA(data));
  }, []);
  if (!a) return <Loading what="Loading analytics" />;
  const cats = Object.entries(a.by_category ?? {}) as [string, Record<string, number>][];
  return (
    <section>
      <PageHead title="Analytics" sub="Where your Connects go and what comes back." />
      <div className="stats">
        <Stat label="Proposals submitted" value={a.proposals_submitted} icon={<IconCheck size={16} />} />
        <Stat label="Connects spent" value={a.connects_spent} icon={<IconCoins size={16} />} />
        <Stat label="p95 run time" value={`${a.p95_run_seconds ?? "–"}s`} icon={<IconBolt size={16} />} />
        <Stat label="Model cost" value={`$${a.cost_usd_total.toFixed(2)}`} hint={`${a.tokens_total} tokens, open models`} icon={<IconChart size={16} />} />
      </div>
      <div className="grid">
        <div className="card">
          <h3>Decisions by category</h3>
          {cats.length ? <CategoryBars rows={cats} /> : <Empty title="No jobs analysed yet" />}
        </div>
        <div className="card">
          <h3>All decisions</h3>
          <Donut label="jobs" data={[
            { label: "Bid", value: cats.reduce((n, [, v]) => n + (v.bid ?? 0), 0), color: "var(--ok)" },
            { label: "Watch", value: cats.reduce((n, [, v]) => n + (v.watch ?? 0), 0), color: "var(--warn)" },
            { label: "Skip", value: cats.reduce((n, [, v]) => n + (v.skip ?? 0), 0), color: "var(--muted-2)" },
          ]} />
        </div>
        <div className="card span2">
          <h3>Top skip reasons</h3>
          {(a.top_skip_reasons ?? []).length === 0 ? <p className="muted">No skips yet.</p> : (
            <ul className="list">
              {(a.top_skip_reasons ?? []).map(([r, n]: [string, number]) => (
                <li key={r}><span>{r}</span><span className="badge">{n}</span></li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
