import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken, type Health } from "../lib/api/client";
import { EmptyArt, IconAlert, IconChart, IconChat, IconInbox, IconLogout, IconPipeline, IconSettings, Logo } from "./Icons";

const NAV = [
  ["/inbox", "Inbox", IconInbox],
  ["/pipeline", "Pipeline", IconPipeline],
  ["/messages", "Messages", IconChat],
  ["/analytics", "Analytics", IconChart],
  ["/settings", "Settings", IconSettings],
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
      <IconAlert size={18} />
      <div>
        <strong>Marketplace unavailable.</strong> New work is queued and will resume automatically when it is back.
        {health.queued ? ` ${health.queued} job(s) queued.` : ""}
        {health.marketplace_detail ? <span className="muted"> ({health.marketplace_detail})</span> : null}
      </div>
    </div>
  );
}

export function Layout() {
  const nav = useNavigate();
  const signOut = () => {
    setToken(null);
    nav("/login");
  };
  return (
    <div className="shell">
      <aside className="side" aria-label="Main navigation">
        <NavLink to="/inbox" className="brand" aria-label="GigBid home">
          <Logo />
          <span>GigBid</span>
        </NavLink>
        <nav>
          {NAV.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <p className="muted small">Nothing is sent until you approve it.</p>
          <button className="ghost full" onClick={signOut}>
            <IconLogout size={16} /> Sign out
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="mobile-top">
          <NavLink to="/inbox" className="brand" aria-label="GigBid">
            <Logo size={26} />
            <span>GigBid</span>
          </NavLink>
          <button className="ghost icon" onClick={signOut} aria-label="Sign out">
            <IconLogout size={18} />
          </button>
        </header>
        <DegradedBanner />
        <main className="page">
          <Outlet />
        </main>
      </div>
      <nav className="tabbar" aria-label="Sections">
        {NAV.map(([to, label, Icon]) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="muted">{sub}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <EmptyArt />
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {what}…
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <p className="note error" role="alert">{error}</p> : null;
}

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span className="muted small">{label}</span>
        {icon && <span className="stat-icon">{icon}</span>}
      </div>
      <div className="stat-value">{value}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}
