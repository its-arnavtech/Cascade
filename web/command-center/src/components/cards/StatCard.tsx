import { ArrowDown, ArrowUp, type LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  detail,
  tone = "default",
  trend,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "default" | "good" | "warn" | "bad" | "teal" | "info" | "violet";
  trend?: "up" | "down";
  icon?: LucideIcon;
}) {
  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : null;
  return (
    <div className={`stat-card ${tone}`}>
      {Icon ? (
        <div className="stat-icon" aria-hidden="true">
          <Icon size={34} strokeWidth={1.8} />
        </div>
      ) : null}
      <div className="stat-card-top">
        <span>{label}</span>
        {TrendIcon ? <TrendIcon size={14} aria-hidden="true" /> : null}
      </div>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}
