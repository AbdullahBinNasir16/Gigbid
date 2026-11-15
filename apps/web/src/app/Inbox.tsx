import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type JobCard } from "../lib/api/client";
import { Badge, Empty, ErrorNote, Loading } from "../components/Layout";

function money(c: JobCard) {
  if (c.budget_max == null) return "budget not stated";
  const unit = c.budget_type === "hourly" ? "/h" : "";
  return c.budget_min && c.budget_min !== c.budget_max ? `$${c.budget_min}–${c.budget_max}${unit}` : `$${c.budget_max}${unit}`;
}

export default function Inbox() {
  const [jobs, setJobs] = useState<JobCard[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [scouting, setScouting] = useState(false);

  const load = useCallback(async () => {
    const { data, error } = await api.GET("/api/jobs");
    if (error) setError("Could not load jobs.");
    else setJobs(data ?? []);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  async function scout() {
    setScouting(true);
    setError(null);
    const res = await api.POST("/api/jobs/scout", { params: { query: { limit: 5 } } });
    setScouting(false);
    if (res.error) setError("Marketplace unavailable; try again shortly.");
    load();
  }

  async function skip(id: string) {
    await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } });
    load();
  }

  const shown = (jobs ?? []).filter((j) => filter === "all" || j.decision === filter || (filter === "pending" && !j.decision));
  return (
    <section>
      <div className="row between">
        <h2>Job inbox</h2>
        <div className="row">
          <label className="inline">
            Show{" "}
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter jobs">
              <option value="all">All</option>
              <option value="bid">Recommended: bid</option>
              <option value="watch">Watch</option>
              <option value="skip">Skip</option>
              <option value="pending">Analysing</option>
            </select>
          </label>
          <button onClick={scout} disabled={scouting}>{scouting ? "Scouting…" : "Scout now"}</button>
        </div>
      </div>
      <ErrorNote error={error} />
      {jobs === null ? (
        <Loading what="Loading jobs" />
      ) : shown.length === 0 ? (
        <Empty title="No jobs yet">
          <p>GigBid scouts your saved searches every few hours. Press <b>Scout now</b> to run them immediately.</p>
        </Empty>
      ) : (
        <ul className="cards" aria-label="Jobs ranked by fit">
          {shown.map((j) => (
            <li key={j.job_id} className="card job" data-testid="job-card">
              <div className="row between">
                <Link to={`/jobs/${encodeURIComponent(j.job_id)}`} className="title">{j.title}</Link>
                {j.decision ? <Badge kind={j.decision}>{j.decision}</Badge> : <Badge kind="pending">{j.status ?? "new"}</Badge>}
              </div>
              <div className="meta">
                <span>{j.category ?? "uncategorised"}</span>
                <span>{money(j)}</span>
                {j.fit != null && <span>fit {(j.fit * 100).toFixed(0)}%</span>}
                {j.price != null && <span>quote ${j.price}</span>}
                {j.connects_cost != null && <span>{j.connects_cost} Connects</span>}
                {j.risk != null && <Badge kind={j.risk >= 0.7 ? "danger" : j.risk >= 0.3 ? "warn" : "ok"}>risk {(j.risk * 100).toFixed(0)}%</Badge>}
                {j.risk_flags?.map((f) => <Badge key={f} kind="flag">{f.replace(/_/g, " ")}</Badge>)}
              </div>
              <div className="row">
                {j.status === "awaiting_approval" && j.thread_id && (
                  <Link className="button" to={`/studio/${encodeURIComponent(j.thread_id)}`}>Review proposal</Link>
                )}
                <Link className="button ghost" to={`/jobs/${encodeURIComponent(j.job_id)}`}>Open</Link>
                {j.decision !== "skip" && j.status !== "submitted" && (
                  <button className="ghost" onClick={() => skip(j.job_id)}>Skip</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
