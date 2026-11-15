import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken, type Health } from "../lib/api/client";

const NAV = [
  ["/inbox", "Inbox"],
  ["/pipeline", "Pipeline"],
  ["/messages", "Messages"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
] as const;

export function DegradedBanner() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { data } = await api.GET("/api/health");
        if (alive) setHealth(data ?? null);
      } catch {
        if (alive) setHealth({ status: "degraded", marketplace: "unavailable", marketplace_detail: "API unreachable", queued: 0 });
      }
    };
    tick();
    const id = setInterval(tick, 10000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  if (!health || health.marketplace === "ok") return null;
  return (
    <div className="banner" role="alert" data-testid="degraded-banner">
      <strong>Marketplace unavailable.</strong> New work is queued and will resume automatically when it is back.
      {health.queued ? ` ${health.queued} job(s) queued.` : ""}
      {health.marketplace_detail ? <span className="muted"> ({health.marketplace_detail})</span> : null}
    </div>
  );
}

export function Layout() {
  const nav = useNavigate();
  return (
    <div className="shell">
      <header className="top">
        <NavLink to="/inbox" className="brand" aria-label="GigBid home">GigBid</NavLink>
        <nav aria-label="Main">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          className="ghost"
          onClick={() => {
            setToken(null);
            nav("/login");
          }}
        >
          Sign out
        </button>
      </header>
      <DegradedBanner />
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted" role="status">{what}…</p>;
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <p className="error" role="alert">{error}</p> : null;
}

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}
