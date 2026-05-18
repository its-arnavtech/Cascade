export type BadgeTone = "default" | "neutral" | "good" | "warn" | "bad" | "teal" | "info" | "dry";

export function Badge({ children, tone = "default" }: { children: React.ReactNode; tone?: BadgeTone }) {
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" aria-hidden="true" />
      {children}
    </span>
  );
}
