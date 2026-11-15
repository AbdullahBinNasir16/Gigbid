import { useEffect, useState } from "react";
import { api } from "../lib/api/client";
import { Empty, Loading } from "../components/Layout";

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
      <h2>Pipeline</h2>
      {status !== "ok" && <p className="error">Marketplace unavailable — showing nothing until it is back.</p>}
      {total === 0 ? <Empty title="No proposals yet"><p>Approved proposals appear here and move as clients view and reply.</p></Empty> : (
        <div className="kanban" role="list">
          {COLS.map((c) => (
            <div key={c} className="col" role="listitem" aria-label={c}>
              <h3>{c} <span className="muted">{board[c]?.length ?? 0}</span></h3>
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
