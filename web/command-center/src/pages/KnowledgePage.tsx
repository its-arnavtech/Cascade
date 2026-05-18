import { FormEvent, useState } from "react";
import { useKnowledgeContext, useKnowledgeSearch, useKnowledgeStats } from "../api/hooks";
import { JsonBlock } from "../components/JsonBlock";
import { StatCard } from "../components/cards/StatCard";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function KnowledgePage() {
  const stats = useKnowledgeStats();
  const search = useKnowledgeSearch();
  const context = useKnowledgeContext();
  const [query, setQuery] = useState("recommendationservice latency runbook");
  const [service, setService] = useState("");
  const [area, setArea] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [showRawContext, setShowRawContext] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    const body = { query, limit: 8, filters: { service: service || undefined, phase: area || undefined } };
    search.mutate(body);
    context.mutate(body);
  }

  function toggleChunk(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Knowledge</h2><p>Source-grounded search and deterministic context packs. No LLM generation.</p></div></div>
      <div className="stats-grid compact">
        <StatCard label="Documents" value={String(stats.data?.documents ?? stats.data?.knowledge_documents ?? "-")} />
        <StatCard label="Chunks" value={String(stats.data?.chunks ?? stats.data?.knowledge_chunks ?? "-")} />
        <StatCard label="Qdrant Points" value={String(stats.data?.qdrant_knowledge_points ?? "-")} />
      </div>
      <form className="knowledge-search" onSubmit={submit}>
        <div className="form-field full"><label htmlFor="knowledge-query">Query</label><textarea id="knowledge-query" rows={3} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Describe the reliability question or runbook topic" />{!query.trim() ? <span className="hint">Enter a search query</span> : null}</div>
        <div className="form-field"><label htmlFor="knowledge-service">Service</label><input id="knowledge-service" value={service} onChange={(e) => setService(e.target.value)} placeholder="recommendationservice" /></div>
        <div className="form-field"><label htmlFor="knowledge-area">Area</label><input id="knowledge-area" value={area} onChange={(e) => setArea(e.target.value)} placeholder="command-center" /></div>
        <button type="submit" disabled={!query.trim()}>Search</button>
      </form>
      <StatusPanel title="Search Results" loading={search.isPending} error={search.error}>
        <DataTable
          caption="Knowledge search results"
          rows={search.data?.results ?? []}
          columns={[
            { key: "score", label: "Score", width: "60px", render: (row) => Number(row.score ?? 0).toFixed(2) },
            { key: "title", label: "Title", width: "180px", render: (row) => <strong>{String(row.title ?? "-")}</strong> },
            { key: "source_type", label: "Source", width: "100px", render: (row) => <span className="muted">{String(row.source_type ?? "-")}</span> },
            { key: "source_path", label: "Path", width: "140px", render: (row) => <span className="muted">{String(row.source_path ?? "-")}</span> },
            { key: "chunk_text", label: "Chunk", render: (row) => {
              const id = String(row.chunk_id ?? row.source_path ?? row.title ?? "");
              const text = String(row.chunk_text ?? "");
              const open = expanded.has(id);
              return <span>{open ? text : `${text.slice(0, 200)}${text.length > 200 ? "..." : ""}`} {text.length > 200 ? <button type="button" className="link-button" onClick={() => toggleChunk(id)}>{open ? "Show less" : "Show more"}</button> : null}</span>;
            } },
          ]}
        />
      </StatusPanel>
      <StatusPanel title="Context Pack" loading={context.isPending} error={context.error}>
        <ContextPack value={context.data ?? { query, evidence_chunks: [], sources: [], limitations: ["Run a search to build a deterministic context pack."] }} showRaw={showRawContext} onToggleRaw={() => setShowRawContext((value) => !value)} />
      </StatusPanel>
    </div>
  );
}

function ContextPack({ value, showRaw, onToggleRaw }: { value: Record<string, unknown>; showRaw: boolean; onToggleRaw: () => void }) {
  const chunks = Array.isArray(value.evidence_chunks) ? value.evidence_chunks : [];
  return (
    <div className="context-pack">
      {chunks.length && !showRaw ? chunks.map((chunk, index) => {
        const record = chunk as Record<string, unknown>;
        return (
          <article className="evidence-card" key={String(record.chunk_id ?? index)}>
            <span>{String(record.source_type ?? record.title ?? `Evidence ${index + 1}`)}</span>
            <p>{String(record.chunk_text ?? record.text ?? "").slice(0, 360)}</p>
          </article>
        );
      }) : <JsonBlock value={value} />}
      <button type="button" className="link-button" onClick={onToggleRaw}>{showRaw ? "Show evidence cards" : "View raw JSON"}</button>
    </div>
  );
}
