// Small SVG charts and diagrams. Every chart has a text label for screen readers.

type Slice = { label: string; value: number; color: string };

/** Donut chart with a center total. */
export function Donut({ data, size = 132, label = "total" }: { data: Slice[]; size?: number; label?: string }) {
  const total = data.reduce((n, d) => n + d.value, 0);
  const r = size / 2 - 12;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut" role="img" aria-label={data.map((d) => `${d.label} ${d.value}`).join(", ")}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track)" strokeWidth="14" />
        {total > 0 && data.map((d) => {
          const len = (d.value / total) * c;
          const el = (
            <circle key={d.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color} strokeWidth="14"
              strokeDasharray={`${Math.max(0, len - 2)} ${c}`} strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} strokeLinecap="butt" />
          );
          offset += len;
          return el;
        })}
        <text x="50%" y="48%" textAnchor="middle" className="donut-n">{total}</text>
        <text x="50%" y="63%" textAnchor="middle" className="donut-l">{label}</text>
      </svg>
      <ul className="donut-legend">
        {data.map((d) => (
          <li key={d.label}><i style={{ background: d.color }} />{d.label}<b>{d.value}</b></li>
        ))}
      </ul>
    </div>
  );
}

/** Half-circle gauge, 0..1 (used for risk). */
export function Gauge({ value, label = "risk" }: { value: number; label?: string }) {
  const v = Math.max(0, Math.min(1, value));
  const r = 52;
  const half = Math.PI * r;
  const color = v >= 0.7 ? "var(--danger)" : v >= 0.3 ? "var(--warn)" : "var(--ok)";
  const word = v >= 0.7 ? "High" : v >= 0.3 ? "Medium" : "Low";
  return (
    <div className="gauge" role="img" aria-label={`${label} ${Math.round(v * 100)} percent, ${word}`}>
      <svg width="132" height="78" viewBox="0 0 132 78">
        <path d="M14 70 A52 52 0 0 1 118 70" fill="none" stroke="var(--track)" strokeWidth="12" strokeLinecap="round" />
        <path d="M14 70 A52 52 0 0 1 118 70" fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={`${half * v} ${half}`} />
        <text x="66" y="62" textAnchor="middle" className="gauge-n">{Math.round(v * 100)}%</text>
      </svg>
      <span className="gauge-l" style={{ color }}>{word} {label}</span>
    </div>
  );
}

/** Thin strength bar 0..1. */
export function Strength({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value));
  const color = v >= 0.5 ? "var(--ok)" : v > 0 ? "var(--warn)" : "var(--muted-2)";
  return (
    <span className="strength" role="img" aria-label={`strength ${Math.round(v * 100)} percent`}>
      <span style={{ width: `${Math.max(4, v * 100)}%`, background: color }} />
    </span>
  );
}

/** Stacked bar for claim support. */
export function SupportBar({ supported, partly, unsupported }: { supported: number; partly: number; unsupported: number }) {
  const total = supported + partly + unsupported;
  if (!total) return null;
  return (
    <div className="support">
      <div className="support-bar" role="img" aria-label={`${supported} supported, ${partly} partly supported, ${unsupported} unsupported claims`}>
        {supported > 0 && <span style={{ flex: supported, background: "var(--ok)" }} />}
        {partly > 0 && <span style={{ flex: partly, background: "var(--warn)" }} />}
        {unsupported > 0 && <span style={{ flex: unsupported, background: "var(--danger)" }} />}
      </div>
      <div className="small muted">{supported} supported · {partly} partly · {unsupported} unsupported</div>
    </div>
  );
}

/** Horizontal funnel of pipeline stages. */
export function Funnel({ stages }: { stages: { label: string; value: number }[] }) {
  const max = Math.max(1, ...stages.map((s) => s.value));
  return (
    <div className="funnel" role="img" aria-label={stages.map((s) => `${s.label} ${s.value}`).join(", ")}>
      {stages.map((s, i) => (
        <div key={s.label} className="funnel-step">
          <div className="funnel-bar" style={{ height: `${18 + (s.value / max) * 62}px`, opacity: 1 - i * 0.09 }} />
          <b>{s.value}</b>
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}

const NODES: [string, string, number, number][] = [
  ["intake", "Intake", 10, 60],
  ["analyst", "Analyst", 110, 14], ["risk", "Risk", 110, 60], ["matcher", "Matcher", 110, 106],
  ["decide", "Decide", 210, 60], ["pricing", "Pricing", 300, 60], ["writer", "Writer", 390, 60],
  ["verifier", "Verify", 480, 60], ["critic", "Critic", 570, 60], ["compliance", "Comply", 660, 60],
  ["approval", "You", 750, 60], ["submit", "Submit", 840, 60],
];
const EDGES: [string, string][] = [
  ["intake", "analyst"], ["intake", "risk"], ["intake", "matcher"], ["analyst", "decide"], ["risk", "decide"],
  ["matcher", "decide"], ["decide", "pricing"], ["pricing", "writer"], ["writer", "verifier"], ["verifier", "critic"],
  ["critic", "compliance"], ["compliance", "approval"], ["approval", "submit"],
];

/** The bid graph as a diagram; nodes that ran are filled, the active one pulses. */
export function GraphMap({ visited, active }: { visited: Set<string>; active?: string }) {
  const pos = Object.fromEntries(NODES.map(([id, , x, y]) => [id, { x, y }]));
  return (
    <div className="graphmap">
      <svg viewBox="0 0 930 140" role="img" aria-label={`Bid graph. Done: ${[...visited].join(", ") || "none"}`}>
        {EDGES.map(([a, b]) => (
          <line key={a + b} x1={pos[a].x + 72} y1={pos[a].y + 13} x2={pos[b].x} y2={pos[b].y + 13}
            stroke={visited.has(b) ? "var(--accent)" : "var(--border)"} strokeWidth="2" />
        ))}
        {NODES.map(([id, label, x, y]) => {
          const done = visited.has(id);
          const isActive = active === id;
          return (
            <g key={id} className={isActive ? "pulse" : ""}>
              <rect x={x} y={y} width="72" height="26" rx="13"
                fill={done ? "var(--accent)" : "var(--surface)"} stroke={done || isActive ? "var(--accent)" : "var(--border)"} strokeWidth="1.5" />
              <text x={x + 36} y={y + 17} textAnchor="middle" fontSize="11" fontWeight="600"
                fill={done ? "var(--accent-text)" : "var(--muted)"}>{label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** Decorative scene for the inbox welcome banner. */
export function WelcomeArt() {
  return (
    <svg width="190" height="120" viewBox="0 0 190 120" aria-hidden="true" className="welcome-art">
      <circle cx="150" cy="30" r="26" fill="rgba(255,255,255,.12)" />
      <rect x="20" y="30" width="110" height="74" rx="12" fill="rgba(255,255,255,.14)" stroke="rgba(255,255,255,.3)" />
      <rect x="32" y="44" width="56" height="7" rx="3.5" fill="rgba(255,255,255,.85)" />
      <rect x="32" y="58" width="84" height="6" rx="3" fill="rgba(255,255,255,.4)" />
      <rect x="32" y="70" width="70" height="6" rx="3" fill="rgba(255,255,255,.4)" />
      <rect x="32" y="84" width="34" height="12" rx="6" fill="rgba(134,239,172,.95)" />
      <rect x="96" y="56" width="74" height="54" rx="12" fill="#fff" />
      <path d="m112 83 8 8 16-16" stroke="var(--brand-1)" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="152" cy="74" r="4" fill="var(--brand-2)" opacity=".5" />
    </svg>
  );
}
