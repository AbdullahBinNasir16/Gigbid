import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, streamUrl } from "../lib/api/client";
import { Empty, PageHead } from "../components/Layout";
import { GraphMap } from "../components/Charts";

type Ev = { type: string; node?: string; summary?: string; at?: number; status?: string; trace_id?: string };
type Trace = { node: string; kind: string; tool?: string | null; result_summary?: string | null; duration_ms?: number | null; tokens?: number };

export default function RunViewer() {
  const { thread = "" } = useParams();
  const [events, setEvents] = useState<Ev[]>([]);
  const [trace, setTrace] = useState<Trace[]>([]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    const es = new EventSource(streamUrl(thread));
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as Ev;
      setEvents((xs) => [...xs, ev]);
      if (ev.type === "run_end" || ev.type === "interrupt") loadTrace();
    };
    loadTrace();
    const poll = setInterval(loadTrace, 4000); // runs executed by the worker update the trace
    return () => {
      es.close();
      clearInterval(poll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread]);

  async function loadTrace() {
    const { data } = await api.GET("/api/runs/{thread_id}/trace", { params: { path: { thread_id: thread } } });
    if (Array.isArray(data)) setTrace(data as Trace[]);
  }

  const waiting = events.some((e) => e.type === "interrupt");
  const visited = new Set<string>([...trace.map((t) => t.node), ...events.filter((e) => e.type === "node" && e.node).map((e) => e.node as string)]);
  if (waiting) visited.add("approval");
  const lastNode = [...events].reverse().find((e) => e.node)?.node;
  return (
    <>
    <PageHead title="Agent run" sub="Live, node by node, with the full trace below." />
    <section className="grid">
      <div className="card span2">
        <h3>Where this job is</h3>
        <GraphMap visited={visited} active={waiting ? "approval" : lastNode} />
      </div>
      <div className="card span2">
        <div className="row between">
          <h2>Live progress</h2>
          <span className={`badge ${live ? "ok" : "pending"}`} aria-live="polite">{live ? "live" : "idle"}</span>
        </div>
        {waiting && <p><Link className="button" to={`/studio/${encodeURIComponent(thread)}`}>Waiting for your approval — review the proposal</Link></p>}
        {events.length === 0 ? <Empty title="No live events"><p>This run is not active. The full trace is below.</p></Empty> : (
          <ol className="timeline" aria-live="polite" data-testid="run-timeline">
            {events.filter((e) => e.type !== "run_start" || e.trace_id).map((e, i) => (
              <li key={i} className={e.type}>
                <b>{e.node ?? e.type}</b> {e.summary && <span>— {e.summary}</span>}
                {e.trace_id && <span className="muted"> trace {e.trace_id}</span>}
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="card span2">
        <h3>Full trace</h3>
        <table className="matrix">
          <thead><tr><th scope="col">Node</th><th scope="col">Event</th><th scope="col">Detail</th><th scope="col">ms</th><th scope="col">tokens</th></tr></thead>
          <tbody>
            {trace.map((t, i) => (
              <tr key={i}><td>{t.node}</td><td>{t.kind}{t.tool ? `: ${t.tool}` : ""}</td><td>{t.result_summary}</td><td>{t.duration_ms ?? ""}</td><td>{t.tokens || ""}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
    </>
  );
}
