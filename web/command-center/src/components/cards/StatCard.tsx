import { ArrowDown, ArrowUp } from "lucide-react";

export function StatCard({
  label,
  value,
  detail,
  tone = "default",
  trend,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "default" | "good" | "warn" | "bad" | "teal" | "info";
  trend?: "up" | "down";
}) {
  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : null;
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-card-top">
        <span>{label}</span>
        {TrendIcon ? <TrendIcon size={14} aria-hidden="true" /> : null}
      </div>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}
