import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, Beaker, BookOpen, FileSearch, Gauge, Home, Info, LifeBuoy, RadioTower, ShieldCheck, Stethoscope } from "lucide-react";

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
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Activity size={24} />
          <div>
            <strong>Cascade</strong>
            <span>Command Center</span>
          </div>
        </div>
        <nav className="nav">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`} end={item.to === "/"}>
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">cascade-system</div>
            <h1>Operator Command Center</h1>
          </div>
          <div className="safe-badge">
            <LifeBuoy size={16} />
            Dry-run safe by default
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
