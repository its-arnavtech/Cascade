import { Link, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bell,
  BookOpen,
  ChevronDown,
  ChevronsLeft,
  FileSearch,
  Gauge,
  Home,
  Info,
  Link2,
  Plus,
  RadioTower,
  RefreshCw,
  Settings,
  ShieldCheck,
  Stethoscope,
  Wrench,
  Zap,
} from "lucide-react";
import { dangerousActionsEnabled } from "../../api/client";
import { useSystemHealth } from "../../api/hooks";

const nav = [
  { to: "/", label: "Overview", icon: Home },
  { to: "/telemetry", label: "Telemetry", icon: RadioTower },
  { to: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { to: "/investigations", label: "Investigations", icon: Stethoscope },
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/chaos", label: "Chaos", icon: Zap },
  { to: "/remediation", label: "Remediation", icon: Wrench },
  { to: "/system", label: "System", icon: Gauge },
  { to: "/incidents", label: "Incidents", icon: FileSearch },
  { to: "/about", label: "About", icon: Info },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const queryClient = useQueryClient();
  const health = useSystemHealth();
  const degradedCount = health.data?.filter((item) => !item.ok).length ?? 0;
  const activeRoute = nav.find((item) => item.to === location.pathname) ?? nav[0];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <strong>Cascade</strong>
            <span>Reliability Command Center</span>
          </div>
        </div>

        <div className={`safety-badge ${dangerousActionsEnabled ? "live" : ""}`}>
          <ShieldCheck size={14} />
          {dangerousActionsEnabled ? "LIVE MODE" : "DRY-RUN SAFE"}
        </div>

        <div className="nav-section-label">Operations</div>
        <nav className="nav" aria-label="Operations">
          {nav.filter((item) => item.to !== "/incidents" && item.to !== "/about").map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? location.pathname === "/" : location.pathname === item.to;
            return (
              <Link key={item.to} to={item.to} className={`nav-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}>
                <Icon />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-secondary">
          <Link to="/about" className={`nav-link ${location.pathname === "/about" ? "active" : ""}`}>
            <Settings />
            <span>Settings</span>
          </Link>
          <Link to="/system" className="nav-link">
            <Link2 />
            <span>Integrations</span>
          </Link>
          <button type="button" className="nav-link">
            <ChevronsLeft />
            <span>Collapse</span>
          </button>
        </div>

        <div className="sidebar-health">
          <span className={`dot ${degradedCount > 0 ? "degraded" : "ok"}`} />
          <span>{degradedCount > 0 ? `${degradedCount} Services Degraded` : "All Systems Operational"}</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <h1>{activeRoute.label}</h1>
          <div className="topbar-meta">
            <button type="button" className="btn" onClick={() => void queryClient.invalidateQueries()}>
              <RefreshCw size={16} />
              Refresh
              <ChevronDown size={14} />
            </button>
            <Link className="btn btn-primary" to="/investigations">
              <Plus size={17} />
              Start Investigation
            </Link>
            <span className="topbar-split" />
            <button type="button" className="btn-icon" aria-label="Notifications">
              <Bell size={18} />
            </button>
            <span className="avatar">JD</span>
            <ChevronDown size={16} />
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
