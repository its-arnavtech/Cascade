export function MiniBars({ values }: { values: Array<{ label: string; value: number }> }) {
  const max = Math.max(1, ...values.map((item) => item.value));
  if (!values.length) return <div className="state">No chartable data yet</div>;
  return (
    <div className="mini-bars">
      {values.map((item) => (
        <div className="bar-row" key={item.label}>
          <span>{item.label}</span>
          <div className="bar-track">
            <div style={{ width: `${Math.max(4, (item.value / max) * 100)}%` }} />
          </div>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}
