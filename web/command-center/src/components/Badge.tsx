export function Badge({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "good" | "warn" | "bad" | "teal" | "dry" | "neutral" }) {
  return <span className={`badge ${tone === "default" ? "neutral" : tone}`}>{children}</span>;
}
