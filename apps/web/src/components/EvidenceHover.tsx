import { useId, useState } from "react";

export type EvidenceItem = { id: string; type: string; project?: string | null; text: string; source: string; outcome?: string | null };

/** A claim that shows the portfolio evidence behind it on hover or keyboard focus. */
export function EvidenceHover({ text, evidence }: { text: string; evidence: EvidenceItem[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="ev" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <span tabIndex={0} aria-describedby={id} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} className="ev-claim">
        {text}
      </span>
      <span id={id} role="tooltip" className={`ev-pop ${open ? "open" : ""}`}>
        {evidence.length === 0 ? (
          <em>No evidence: this claim is not backed by your portfolio.</em>
        ) : (
          evidence.map((e) => (
            <span key={e.id} className="ev-item">
              <b>{e.project ?? e.type}</b> <small>({e.type}, {e.source}{e.outcome ? `, ${e.outcome}` : ""})</small>
              <br />
              {e.text.slice(0, 280)}
            </span>
          ))
        )}
      </span>
    </span>
  );
}
