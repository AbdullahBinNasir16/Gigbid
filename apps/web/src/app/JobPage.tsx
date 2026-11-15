import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type JobDetail } from "../lib/api/client";
import { Badge, ErrorNote, Loading } from "../components/Layout";
import { Ring } from "../components/Icons";

type Ev = { id: string; type: string; project?: string | null; text: string; source: string };

export default function JobPage() {
  const { id = "" } = useParams();
  const [d, setD] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } });
      if (!alive) return;
      if (error) setError("Job not found.");
      else setD(data ?? null);
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [id]);

  async function run() {
    await api.POST("/api/jobs/{job_id}/run", { params: { path: { job_id: id } } });
  }

  if (error) return <ErrorNote error={error} />;
  if (!d) return <Loading what="Loading job" />;
  const a = (d.analysis ?? {}) as Record<string, any>;
  const spec = a.job_spec, risk = a.risk, fit = a.fit, price = a.price, decision = a.decision;
  const evidence: Ev[] = a.evidence ?? [];
  const byId = Object.fromEntries(evidence.map((e) => [e.id, e]));
  const job = d.job as Record<string, any>;

  return (
    <section className="grid">
      <div className="card span2">
        <div className="row between">
          <h2>{job.title}</h2>
          {decision && <Badge kind={decision.decision}>{decision.decision}</Badge>}
        </div>
        <p className="untrusted" aria-label="Job post (client text, untrusted)">{job.description}</p>
        <div className="row">
          {d.status === "awaiting_approval" && d.thread_id && <Link className="button" to={`/studio/${encodeURIComponent(d.thread_id)}`}>Review proposal</Link>}
          {d.thread_id && <Link className="button ghost" to={`/runs/${encodeURIComponent(d.thread_id)}`}>Agent run</Link>}
          {!d.thread_id && <button onClick={run}>Analyse</button>}
          <span className="muted">status: {d.status}</span>
        </div>
      </div>

      {decision && (
        <div className="card">
          <div className="row between top"><h3>Bid or skip</h3><Ring value={decision.fit_score} size={52} /></div>
          <ul>{decision.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
          <p className="muted">fit {(decision.fit_score * 100).toFixed(0)}% · risk {(decision.risk_score * 100).toFixed(0)}%</p>
        </div>
      )}

      {risk && (
        <div className="card">
          <h3>Risk report</h3>
          <p>{risk.explanation}</p>
          <div className="row">{risk.flags.map((f: string) => <Badge key={f} kind="flag">{f.replace(/_/g, " ")}</Badge>)}</div>
          {risk.injection_detected && <p className="warn">Instructions aimed at AI assistants were found in this post and ignored.</p>}
        </div>
      )}

      {spec && (
        <div className="card">
          <h3>JobSpec</h3>
          <p><b>Skills:</b> {spec.required_skills.join(", ") || "none listed"}</p>
          <p><b>Budget:</b> {spec.budget_type} {spec.budget_min ?? "?"}–{spec.budget_max ?? "?"}</p>
          {spec.screening_questions.length > 0 && <p><b>Screening:</b> {spec.screening_questions.join(" · ")}</p>}
          {spec.is_vague && <Badge kind="warn">vague post</Badge>}
        </div>
      )}

      {price && (
        <div className="card">
          <h3>Price</h3>
          <p className="big">${price.amount} {price.budget_type === "hourly" ? "/h" : "fixed"}</p>
          <p>{price.rationale}</p>
          <p className="muted">{price.connects_cost} Connects · {price.worth_it ? "worth it" : "not worth it"}</p>
        </div>
      )}

      {fit && (
        <div className="card span2">
          <h3>Requirement → evidence</h3>
          <table className="matrix">
            <thead><tr><th scope="col">Requirement</th><th scope="col">Portfolio proof</th><th scope="col">Strength</th></tr></thead>
            <tbody>
              {fit.requirement_matches.map((m: any) => (
                <tr key={m.requirement}>
                  <td>{m.requirement}</td>
                  <td>{m.evidence_ids.length ? m.evidence_ids.map((i: string) => <span key={i} className="chip-ev" title={byId[i]?.text}>{byId[i]?.project ?? i}</span>) : <span className="muted">no evidence</span>}</td>
                  <td>{(m.strength * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          {fit.missing_skills.length > 0 && <p className="muted">Missing: {fit.missing_skills.join(", ")}</p>}
        </div>
      )}
    </section>
  );
}
