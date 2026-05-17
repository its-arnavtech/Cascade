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
  const [phase, setPhase] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const body = { query, limit: 8, filters: { service: service || undefined, phase: phase || undefined } };
    search.mutate(body);
    context.mutate(body);
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Knowledge</h2><p>Source-grounded search and deterministic context packs. No LLM generation.</p></div></div>
      <div className="stats-grid compact">
        <StatCard label="Documents" value={String(stats.data?.documents ?? stats.data?.knowledge_documents ?? "-")} />
        <StatCard label="Chunks" value={String(stats.data?.chunks ?? stats.data?.knowledge_chunks ?? "-")} />
        <StatCard label="Qdrant Points" value={String(stats.data?.qdrant_knowledge_points ?? "-")} />
      </div>
      <form className="form-row" onSubmit={submit}>
        <label className="form-field">Query<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search query" /></label>
        <label className="form-field">Service<input value={service} onChange={(e) => setService(e.target.value)} placeholder="service filter" /></label>
        <label className="form-field">Phase<input value={phase} onChange={(e) => setPhase(e.target.value)} placeholder="phase filter" /></label>
        <button className="btn btn-primary" type="submit">Search</button>
      </form>
      <StatusPanel title="Search Results" loading={search.isPending} error={search.error}>
        <DataTable rows={search.data?.results ?? []} columns={[{ key: "score", label: "Score" }, { key: "title", label: "Title" }, { key: "source_type", label: "Source" }, { key: "source_path", label: "Path" }, { key: "chunk_text", label: "Chunk" }]} />
      </StatusPanel>
      <StatusPanel title="Context Pack" loading={context.isPending} error={context.error}>
        <JsonBlock value={context.data ?? { query, evidence_chunks: [], sources: [], limitations: ["Run a search to build a deterministic context pack."] }} />
      </StatusPanel>
    </div>
  );
}
