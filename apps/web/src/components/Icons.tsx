// Small inline icon set (stroke icons, inherit currentColor). No icon font, no network.
import type { ReactNode, SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: P & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {children}
    </svg>
  );
}

export const IconInbox = (p: P) => <Svg {...p}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></Svg>;
export const IconPipeline = (p: P) => <Svg {...p}><rect x="3" y="4" width="5" height="16" rx="1.5" /><rect x="10" y="4" width="5" height="10" rx="1.5" /><rect x="17" y="4" width="4" height="6" rx="1.5" /></Svg>;
export const IconChat = (p: P) => <Svg {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Svg>;
export const IconChart = (p: P) => <Svg {...p}><path d="M3 3v18h18" /><path d="m7 15 4-4 3 3 5-6" /></Svg>;
export const IconSettings = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></Svg>;
export const IconLogout = (p: P) => <Svg {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></Svg>;
export const IconSearch = (p: P) => <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Svg>;
export const IconShield = (p: P) => <Svg {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></Svg>;
export const IconCheck = (p: P) => <Svg {...p}><path d="M20 6 9 17l-5-5" /></Svg>;
export const IconAlert = (p: P) => <Svg {...p}><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></Svg>;
export const IconSpark = (p: P) => <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></Svg>;
export const IconArrow = (p: P) => <Svg {...p}><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></Svg>;
export const IconCoins = (p: P) => <Svg {...p}><ellipse cx="9" cy="7" rx="6" ry="3" /><path d="M3 7v5c0 1.66 2.69 3 6 3s6-1.34 6-3V7" /><path d="M15 11.2c3.4.3 6 1.6 6 3.3 0 1.66-2.69 3-6 3-1.5 0-2.9-.28-4-.74" /></Svg>;
export const IconBolt = (p: P) => <Svg {...p}><path d="M13 2 3 14h9l-1 8 10-12h-9z" /></Svg>;

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="gb-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--brand-1)" />
          <stop offset="1" stopColor="var(--brand-2)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#gb-g)" />
      <path d="M21.5 11.2A7 7 0 1 0 23 16h-6.5" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="23" cy="9" r="2.2" fill="#fff" opacity=".9" />
    </svg>
  );
}

/** Circular score meter, 0..1. */
export function Ring({ value, size = 46, label }: { value: number | null | undefined; size?: number; label?: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const tone = v >= 0.5 ? "var(--ok)" : v >= 0.35 ? "var(--warn)" : "var(--muted-2)";
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={`${label ?? "fit"} ${Math.round(v * 100)} percent`}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--track)" strokeWidth="5" fill="none" />
        {value != null && (
          <circle cx={size / 2} cy={size / 2} r={r} stroke={tone} strokeWidth="5" fill="none" strokeLinecap="round"
            strokeDasharray={`${c * v} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        )}
      </svg>
      <span>{value == null ? "–" : Math.round(v * 100)}</span>
    </div>
  );
}

/** Friendly illustration for empty states. */
export function EmptyArt() {
  return (
    <svg width="132" height="96" viewBox="0 0 132 96" aria-hidden="true" className="empty-art">
      <rect x="18" y="20" width="96" height="64" rx="12" fill="var(--surface-2)" stroke="var(--border)" />
      <rect x="30" y="34" width="44" height="7" rx="3.5" fill="var(--track)" />
      <rect x="30" y="48" width="66" height="7" rx="3.5" fill="var(--track)" />
      <rect x="30" y="62" width="34" height="7" rx="3.5" fill="var(--track)" />
      <circle cx="100" cy="22" r="14" fill="var(--accent-soft)" />
      <path d="M94 22h12M100 16v12" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}
