import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ApprovalItem } from "../lib/api/client";
import { Badge, Empty, ErrorNote, Loading, PageHead } from "../components/Layout";
import { EvidenceHover, type EvidenceItem } from "../components/EvidenceHover";
import { SupportBar } from "../components/Charts";

type Claim = { text: string; evidence_ids: string[]; support: string };

export default function Studio() {
  const { thread = "" } = useParams();
  const nav = useNavigate();
  const [item, setItem] = useState<ApprovalItem | null>(null);
  const [missing, setMissing] = useState(false);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const { data } = await api.GET("/api/approvals/{thread_id}", { params: { path: { thread_id: thread } } });
      if (!data) return setMissing(true);
      setItem(data);
      setText((data.payload as any).draft?.cover_letter ?? "");
    })();
  }, [thread]);

  const p = (item?.payload ?? {}) as Record<string, any>;
  const evidence: EvidenceItem[] = p.evidence ?? [];
  const byId = useMemo(() => Object.fromEntries(evidence.map((e) => [e.id, e])), [evidence]);
  const claims: Claim[] = p.draft?.claims ?? [];
  const original = p.draft?.cover_letter ?? "";
  const edited = text.trim() !== original.trim();

  async function act(action: "approve" | "edit" | "reject") {
    if (action === "reject" && !reason.trim()) return setError("Give a reason for rejecting; GigBid learns from it.");
    setBusy(true);
    setError(null);
    const body = action === "edit" ? { action, edited_text: text } : action === "reject" ? { action, reason } : { action };
    const { error } = await api.POST("/api/approvals/{thread_id}", { params: { path: { thread_id: thread } }, body });
    setBusy(false);
    if (error) return setError("Could not record the decision. Try again.");
    nav(`/runs/${encodeURIComponent(thread)}`);
  }

  if (missing) return <Empty title="Nothing waiting here"><p>This proposal was already decided. <Link to="/inbox">Back to inbox</Link></p></Empty>;
  if (!item) return <Loading what="Loading draft" />;

  return (
    <>
    <PageHead title="Proposal studio" sub={item.title} />
    <section className="grid">
      <div className="card span2">
        <label htmlFor="draft">Draft (edit freely; edits are re-checked by Compliance and teach your style memory)</label>
        <textarea id="draft" data-testid="draft-editor" value={text} onChange={(e) => setText(e.target.value)} rows={12} />
        <h3>Claims and their evidence</h3>
        <SupportBar supported={claims.filter((c) => c.support === "supported").length}
          partly={claims.filter((c) => c.support === "partly_supported").length}
          unsupported={claims.filter((c) => c.support === "unsupported").length} />
        {claims.length === 0 ? <p className="muted">No experience claims detected.</p> : (
          <ul className="claims">
            {claims.map((c) => (
              <li key={c.text}>
                <Badge kind={c.support === "supported" ? "ok" : c.support === "partly_supported" ? "warn" : "danger"}>{c.support.replace("_", " ")}</Badge>{" "}
                <EvidenceHover text={c.text} evidence={c.evidence_ids.map((i) => byId[i]).filter(Boolean)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3>What will be sent</h3>
        <p>Action: <b>{p.preview?.action}</b></p>
        <p>Price: <b>${p.price?.amount}</b> {p.price?.budget_type}</p>
        <p>Connects: <b>{p.preview?.connects_cost}</b>{p.preview?.connects_balance_after != null && <> · balance after <b>{p.preview.connects_balance_after}</b></>}</p>
        <p className="muted">{p.price?.rationale}</p>
      </div>

      <div className="card">
        <h3>Checks</h3>
        <p>Compliance: <Badge kind={p.compliance?.verdict === "block" ? "danger" : "ok"}>{p.compliance?.verdict ?? "n/a"}</Badge></p>
        {p.compliance?.reasons?.map((r: string) => <p key={r} className="error">{r}</p>)}
        {p.compliance?.removed_items?.length > 0 && <p className="muted">Removed: {p.compliance.removed_items.join("; ")}</p>}
        {p.risk && <p>Risk: {(p.risk.score * 100).toFixed(0)}% — {p.risk.explanation}</p>}
      </div>

      <div className="card span2">
        <ErrorNote error={error} />
        <div className="row">
          <button className="primary" data-testid="approve" onClick={() => act(edited ? "edit" : "approve")} disabled={busy}>
            {edited ? "Approve with my edits" : "Approve and send as draft"}
          </button>
          <input aria-label="Reason for rejecting" placeholder="Reason (required to reject)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="reject-reason" />
          <button className="danger" data-testid="reject" onClick={() => act("reject")} disabled={busy}>Reject</button>
        </div>
        <p className="muted">Nothing is sent until you approve. Approval creates the proposal on the marketplace and spends the Connects shown above, exactly once.</p>
      </div>
    </section>
    </>
  );
}
