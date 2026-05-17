import { AlertCircle } from "lucide-react";

export function StatusPanel({ title, children, error, loading }: { title: string; children: React.ReactNode; error?: unknown; loading?: boolean }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      {loading ? (
        <div className="shimmer-stack" aria-busy="true" aria-label={`${title} loading`}>
          <span />
          <span />
          <span />
        </div>
      ) : null}
      {error ? (
        <div className="state error">
          <AlertCircle size={16} aria-hidden="true" />
          {error instanceof Error ? error.message : String(error)}
        </div>
      ) : null}
      {!loading && !error ? children : null}
    </section>
  );
}
