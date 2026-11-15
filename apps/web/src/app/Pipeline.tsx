import { useEffect, useState } from "react";
import { api } from "../lib/api/client";
import { Empty, Loading, PageHead } from "../components/Layout";
import { Funnel } from "../components/Charts";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];
type Card = { proposal_id: string; job_id: string; amount: number; state: string };

export default function Pipeline() {
  const [board, setBoard] = useState<Record<string, Card[]> | null>(null);
  const [status, setStatus] = useState("ok");
  useEffect(() => {
    const load = async () => {
      const { data } = await api.GET("/api/proposals/pipeline");
      const d = data as any;
      if (d) {
        setBoard(d.columns);
        setStatus(d.marketplace);
      }
    };
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);
  if (!board) return <Loading what="Loading pipeline" />;
  const total = COLS.reduce((n, c) => n + (board[c]?.length ?? 0), 0);
  return (
    <section>
      <PageHead title="Pipeline" sub="Every approved proposal, from draft to hired." />
      {status !== "ok" && <p className="error">Marketplace unavailable — showing nothing until it is back.</p>}
      <div className="card funnel-card">
        <h3>Funnel</h3>
        <Funnel stages={[
          { label: "Sent", value: total - (board.drafted?.length ?? 0) },
          { label: "Viewed", value: ["viewed", "replied", "interview", "hired"].reduce((n, c) => n + (board[c]?.length ?? 0), 0) },
          { label: "Replied", value: ["replied", "interview", "hired"].reduce((n, c) => n + (board[c]?.length ?? 0), 0) },
          { label: "Interview", value: ["interview", "hired"].reduce((n, c) => n + (board[c]?.length ?? 0), 0) },
          { label: "Hired", value: board.hired?.length ?? 0 },
        ]} />
      </div>
      {total === 0 ? <Empty title="No proposals yet"><p>Approved proposals appear here and move as clients view and reply.</p></Empty> : (
        <div className="kanban" role="list">
          {COLS.map((c) => (
            <div key={c} className="col" role="listitem" aria-label={c}>
              <h3><span>{c}</span><span className="badge">{board[c]?.length ?? 0}</span></h3>
              {(board[c] ?? []).map((p) => (
                <div key={p.proposal_id} className="card mini">
                  <b>{p.job_id}</b>
                  <div className="muted">${p.amount}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
