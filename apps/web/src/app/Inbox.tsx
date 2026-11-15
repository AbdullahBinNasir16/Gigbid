import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type JobCard } from "../lib/api/client";
import { Badge, Empty, ErrorNote, Loading, PageHead, Stat } from "../components/Layout";
import { Donut, WelcomeArt } from "../components/Charts";
import { IconArrow, IconBolt, IconChart, IconCheck, IconSearch, IconShield, Ring } from "../components/Icons";

function money(c: JobCard) {
  if (c.budget_max == null) return "Budget not stated";
  const unit = c.budget_type === "hourly" ? "/h" : " fixed";
  return c.budget_min && c.budget_min !== c.budget_max ? `$${c.budget_min}–${c.budget_max}${unit}` : `$${c.budget_max}${unit}`;
}

const CATEGORY: Record<string, string> = { ai_ml: "AI / ML", web_dev: "Web development", data_analytics: "Data analytics", mobile_dev: "Mobile", design: "Design", marketing: "Marketing", writing: "Writing", admin: "Admin", video: "Video", other: "Other" };

const FILTERS: [string, string][] = [["all", "All"], ["bid", "Bid"], ["watch", "Watch"], ["skip", "Skip"], ["pending", "Analysing"]];

export default function Inbox() {
  const [jobs, setJobs] = useState<JobCard[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [scouting, setScouting] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data, error } = await api.GET("/api/jobs");
      if (error) setError("Could not load jobs.");
      else setJobs(data ?? []);
    } catch {
      setError("Can't reach the GigBid server.");
      setJobs((j) => j ?? []);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  async function scout() {
    setScouting(true);
    setError(null);
    try {
      const res = await api.POST("/api/jobs/scout", { params: { query: { limit: 5 } } });
      if (res.error) setError("Marketplace unavailable; try again shortly.");
    } catch {
      setError("Marketplace unavailable; try again shortly.");
    }
    setScouting(false);
    load();
  }

  async function skip(id: string) {
    await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } });
    load();
  }

  const all = jobs ?? [];
  const shown = all.filter((j) => filter === "all" || j.decision === filter || (filter === "pending" && !j.decision));
  const count = (f: string) => all.filter((j) => (f === "pending" ? !j.decision : j.decision === f)).length;

  return (
    <section>
      <PageHead title="Job inbox" sub="New jobs from your saved searches, ranked by fit.">
        <button className="primary" onClick={scout} disabled={scouting}>
          <IconSearch size={16} /> {scouting ? "Scouting…" : "Scout now"}
        </button>
      </PageHead>

      <div className="welcome">
        <div className="welcome-text">
          <span className="eyebrow">Today</span>
          <h2>{count("bid") ? `${count("bid")} job${count("bid") > 1 ? "s" : ""} worth a bid` : "Let's find your next client"}</h2>
          <p>{all.filter((j) => j.status === "awaiting_approval").length
            ? `${all.filter((j) => j.status === "awaiting_approval").length} proposal draft(s) are ready for your review.`
            : "GigBid checks every post for fit, price and scams before drafting anything."}</p>
        </div>
        <WelcomeArt />
        <div className="welcome-chart">
          <Donut size={120} label="jobs" data={[
            { label: "Bid", value: count("bid"), color: "var(--ok)" },
            { label: "Watch", value: count("watch"), color: "var(--warn)" },
            { label: "Skip", value: count("skip"), color: "var(--muted-2)" },
          ]} />
        </div>
      </div>

      <div className="stats">
        <Stat label="Recommended bids" value={count("bid")} icon={<IconBolt size={16} />} />
        <Stat label="Waiting for you" value={all.filter((j) => j.status === "awaiting_approval").length} icon={<IconCheck size={16} />} />
        <Stat label="Risky or scam" value={all.filter((j) => (j.risk ?? 0) >= 0.7).length} icon={<IconShield size={16} />} />
        <Stat label="Analysed" value={all.filter((j) => j.decision).length} icon={<IconChart size={16} />} />
      </div>

      <div className="chips" role="group" aria-label="Filter jobs">
        {FILTERS.map(([k, label]) => (
          <button key={k} className={`chip ${filter === k ? "on" : ""}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>
            {label}
            {k !== "all" && <span className="chip-n">{count(k)}</span>}
          </button>
        ))}
      </div>

      <ErrorNote error={error} />
      {jobs === null ? (
        <Loading what="Loading jobs" />
      ) : shown.length === 0 ? (
        <Empty title={all.length ? "Nothing in this filter" : "No jobs yet"}>
          <p>GigBid scouts your saved searches every few hours. Press <b>Scout now</b> to run them immediately.</p>
        </Empty>
      ) : (
        <ul className="cards" aria-label="Jobs ranked by fit">
          {shown.map((j) => (
            <li key={j.job_id} className={`card job ${j.decision ?? "pending"}`} data-testid="job-card">
              <Ring value={j.fit} label="fit" />
              <div className="job-body">
                <div className="row between top">
                  <Link to={`/jobs/${encodeURIComponent(j.job_id)}`} className="title">{j.title}</Link>
                  {j.decision ? <Badge kind={j.decision}>{j.decision}</Badge> : <Badge kind="pending">{j.status ?? "new"}</Badge>}
                </div>
                <div className="meta">
                  <span>{CATEGORY[j.category ?? ""] ?? (j.category ?? "Uncategorised").replace(/_/g, " ")}</span>
                  <span>{money(j)}</span>
                  {j.price != null && <span>Quote <b>${j.price}</b></span>}
                  {j.connects_cost != null && <span>{j.connects_cost} Connects</span>}
                  {j.risk != null && (
                    <Badge kind={j.risk >= 0.7 ? "danger" : j.risk >= 0.3 ? "warn" : "ok"}>risk {(j.risk * 100).toFixed(0)}%</Badge>
                  )}
                  {j.risk_flags?.map((f) => <Badge key={f} kind="flag">{f.replace(/_/g, " ")}</Badge>)}
                </div>
                <div className="row actions">
                  {j.status === "awaiting_approval" && j.thread_id && (
                    <Link className="button primary sm" to={`/studio/${encodeURIComponent(j.thread_id)}`}>
                      Review proposal <IconArrow size={14} />
                    </Link>
                  )}
                  <Link className="button ghost sm" to={`/jobs/${encodeURIComponent(j.job_id)}`}>Open</Link>
                  {j.decision !== "skip" && j.status !== "submitted" && (
                    <button className="ghost sm" onClick={() => skip(j.job_id)}>Skip</button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
