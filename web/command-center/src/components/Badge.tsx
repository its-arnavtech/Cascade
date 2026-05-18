export type BadgeTone = "default" | "neutral" | "good" | "warn" | "bad" | "teal" | "info" | "dry";

export function Badge({ children, tone = "default" }: { children: React.ReactNode; tone?: BadgeTone }) {
  return <span className={`badge ${tone === "default" ? "neutral" : tone}`}>{children}</span>;
}
