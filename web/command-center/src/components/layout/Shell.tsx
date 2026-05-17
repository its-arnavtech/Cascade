import { NavLink } from "react-router-dom";
import { AlertTriangle, Beaker, BookOpen, FileSearch, Gauge, Home, Info, RadioTower, RefreshCw, Shield, ShieldCheck, Stethoscope } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { dangerousActionsEnabled } from "../../api/client";
import { useSystemHealth } from "../../api/hooks";

const nav = [
  { to: "/", label: "Overview", icon: Home },
  { to: "/telemetry", label: "Telemetry", icon: RadioTower },
  { to: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { to: "/incidents", label: "Incidents", icon: FileSearch },
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/investigations", label: "Investigations", icon: Stethoscope },
  { to: "/chaos", label: "Chaos", icon: Beaker },
  { to: "/remediation", label: "Remediation", icon: ShieldCheck },
  { to: "/system", label: "System", icon: Gauge },
  { to: "/about", label: "About", icon: Info },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const health = useSystemHealth();
  const queryClient = useQueryClient();
  const degraded = health.data?.filter((item) => !item.ok).length ?? 0;
  const liveMode = readDangerousFlag(health.data) ?? dangerousActionsEnabled;
  const updated = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3 28 10v12l-12 7-12-7V10L16 3Z" />
            <path d="M10 13h12M10 19h12M16 7v18" />
          </svg>
          <div>
            <strong>Cascade</strong>
            <span>Command Center</span>
          </div>
        </div>
        <div className={`safe-badge ${liveMode ? "live" : ""}`}>
          <Shield size={14} />
          {liveMode ? "LIVE MODE" : "DRY-RUN SAFE"}
        </div>
        <div className="nav-section">Operations</div>
        <nav className="nav">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`} end={item.to === "/"}>
                {({ isActive }) => (
                  <>
                    <Icon size={20} aria-hidden="true" />
                    <span>{item.label}</span>
                    {isActive ? <span className="sr-only" aria-current="page">current page</span> : null}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="service-mini">
          <span className={`service-dot ${degraded ? "warn" : "ok"}`} />
          <span>{degraded ? `${degraded} degraded` : "Services OK"}</span>
        </div>
        <div className="sidebar-foot">
          <span>v0.1</span>
          <span>local kind</span>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">cascade-system</div>
            <h1>Operator Command Center</h1>
            <p>Kubernetes-native reliability operations</p>
          </div>
          <div className="topbar-actions">
            <span>Updated {updated}</span>
            <button type="button" className="icon-button" aria-label="Refresh dashboard data" onClick={() => void queryClient.invalidateQueries()}>
              <RefreshCw size={16} />
            </button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

function readDangerousFlag(items: unknown): boolean | undefined {
  if (!Array.isArray(items)) return undefined;
  for (const item of items) {
    const data = (item as { data?: unknown }).data as Record<string, unknown> | undefined;
    if (typeof data?.dangerous_actions_enabled === "boolean") return data.dangerous_actions_enabled;
  }
  return undefined;
}
