import { useEffect, useState } from "react";
import { api } from "../lib/api/client";
import { Loading } from "../components/Layout";

export default function Analytics() {
  const [a, setA] = useState<any>(null);
  useEffect(() => {
    api.GET("/api/analytics").then(({ data }) => setA(data));
  }, []);
  if (!a) return <Loading what="Loading analytics" />;
  const cats = Object.entries(a.by_category ?? {}) as [string, Record<string, number>][];
  return (
    <section className="grid">
      <div className="card"><h3>Proposals submitted</h3><p className="big">{a.proposals_submitted}</p></div>
      <div className="card"><h3>Connects spent</h3><p className="big">{a.connects_spent}</p></div>
      <div className="card"><h3>p95 run time</h3><p className="big">{a.p95_run_seconds ?? "–"}s</p></div>
      <div className="card"><h3>Model cost</h3><p className="big">${a.cost_usd_total.toFixed(2)}</p><p className="muted">{a.tokens_total} tokens (open models)</p></div>
      <div className="card span2">
        <h3>By category</h3>
        <table className="matrix">
          <thead><tr><th scope="col">Category</th><th scope="col">Bid</th><th scope="col">Watch</th><th scope="col">Skip</th><th scope="col">Submitted</th></tr></thead>
          <tbody>{cats.map(([c, v]) => <tr key={c}><td>{c}</td><td>{v.bid ?? 0}</td><td>{v.watch ?? 0}</td><td>{v.skip ?? 0}</td><td>{v.submitted ?? 0}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card span2">
        <h3>Top skip reasons</h3>
        <ul>{(a.top_skip_reasons ?? []).map(([r, n]: [string, number]) => <li key={r}>{r} — {n}</li>)}</ul>
      </div>
    </section>
  );
}
