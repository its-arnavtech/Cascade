export interface Column<T extends object> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
}

export function DataTable<T extends object>({ rows, columns, empty = "No records found" }: { rows: T[]; columns: Column<T>[]; empty?: string }) {
  if (!rows.length) return <div className="state">{empty}</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => (
                <td key={column.key}>{column.render ? column.render(row) : formatCell((row as Record<string, unknown>)[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function rowKey(row: object, index: number): string {
  const record = row as Record<string, unknown>;
  return String(record.id ?? record.event_id ?? record.anomaly_id ?? record.incident_id ?? record.plan_id ?? record.run_id ?? record.investigation_id ?? record.execution_id ?? index);
}

function formatCell(value: unknown): React.ReactNode {
  if (value === undefined || value === null || value === "") return <span className="muted">-</span>;
  if (typeof value === "object") return <code>{JSON.stringify(value).slice(0, 160)}</code>;
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}
