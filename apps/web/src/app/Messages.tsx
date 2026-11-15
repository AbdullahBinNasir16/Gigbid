import { useEffect, useState } from "react";
import { api } from "../lib/api/client";
import { Empty, ErrorNote, Loading } from "../components/Layout";

type Thread = { thread_id: string; job_id: string; message_count: number; last_message_at: string };
type Msg = { message_id: string; sender: string; text: string; sent_at: string };

export default function Messages() {
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [pending, setPending] = useState<any>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const { data } = await api.GET("/api/messages/threads");
      setThreads(((data as any)?.threads ?? []) as Thread[]);
    })();
  }, []);

  async function open(id: string) {
    setActive(id);
    setNote(null);
    const { data } = await api.GET("/api/messages/threads/{thread_id}", { params: { path: { thread_id: id } } });
    const d = data as any;
    setMsgs(d?.messages ?? []);
    setPending(d?.pending ?? null);
    setDraft(d?.pending?.message_text ?? "");
  }

  async function suggest() {
    if (!active) return;
    const { data } = await api.POST("/api/messages/threads/{thread_id}/suggest", { params: { path: { thread_id: active } } });
    const d = data as any;
    if (d?.pending) {
      setPending(d.pending);
      setDraft(d.pending.message_text);
    } else setNote(d?.reason ?? "No reply suggested.");
  }

  async function decide(action: "approve" | "edit" | "reject") {
    if (!active) return;
    const body = action === "edit" ? { action, edited_text: draft } : action === "reject" ? { action, reason: "not now" } : { action };
    const { data } = await api.POST("/api/messages/threads/{thread_id}/approve", { params: { path: { thread_id: active } }, body });
    setNote(`Status: ${(data as any)?.status ?? "done"}`);
    open(active);
  }

  if (!threads) return <Loading what="Loading conversations" />;
  return (
    <section className="grid">
      <div className="card">
        <h2>Messages</h2>
        {threads.length === 0 ? <Empty title="No client replies yet" /> : (
          <ul className="list">
            {threads.map((t) => (
              <li key={t.thread_id}><button className={active === t.thread_id ? "" : "ghost"} onClick={() => open(t.thread_id)}>{t.job_id} · {t.message_count} msgs</button></li>
            ))}
          </ul>
        )}
      </div>
      <div className="card">
        {!active ? <p className="muted">Pick a conversation.</p> : (
          <>
            <ol className="chat">{msgs.map((m) => <li key={m.message_id} className={m.sender}><b>{m.sender}</b>: <span className="untrusted">{m.text}</span></li>)}</ol>
            {pending ? (
              <>
                <label htmlFor="reply">Suggested reply (approve before it is sent)</label>
                <textarea id="reply" rows={5} value={draft} onChange={(e) => setDraft(e.target.value)} />
                {pending.preview?.payload?.slots?.length > 0 && <p className="muted">Interview slots offered: {pending.preview.payload.slots.map((s: any) => s.start.slice(0, 16).replace("T", " ")).join(", ")} UTC</p>}
                <div className="row">
                  <button onClick={() => decide(draft.trim() !== pending.message_text.trim() ? "edit" : "approve")}>Approve and send</button>
                  <button className="danger" onClick={() => decide("reject")}>Discard</button>
                </div>
              </>
            ) : <button onClick={suggest}>Suggest a reply</button>}
            <ErrorNote error={note} />
          </>
        )}
      </div>
    </section>
  );
}
