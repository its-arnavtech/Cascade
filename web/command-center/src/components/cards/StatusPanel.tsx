export function StatusPanel({ title, children, error, loading }: { title: string; children: React.ReactNode; error?: unknown; loading?: boolean }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      {loading ? <div className="state loading"><span className="shimmer-row" /><span className="shimmer-row" /><span className="shimmer-row" /></div> : null}
      {error ? <div className="state error">{error instanceof Error ? error.message : String(error)}</div> : null}
      {!loading && !error ? children : null}
    </section>
  );
}
