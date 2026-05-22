import { FormEvent, useState } from "react";
import { useAnalyzeCausality, useAnalyzeRca, useCausalIncidents, useCausalReport, useRcaReports } from "../api/hooks";
import { Badge } from "../components/Badge";
import { BlastRadiusPanel, CausalReportPanel, EvidenceReportPanel, RcaReportPanel } from "../components/IntelligencePanels";
import { JsonBlock } from "../components/JsonBlock";
import { StatusPanel } from "../components/cards/StatusPanel";
import { DataTable } from "../components/tables/DataTable";

export function CausalityPage() {
  const reports = useCausalIncidents();
  const rcaReports = useRcaReports();
  const analyze = useAnalyzeCausality();
  const analyzeRca = useAnalyzeRca();
  const report = useCausalReport();
  const [targetService, setTargetService] = useState("");
  const [selected, setSelected] = useState<Record<string, unknown> | undefined>();

  function analyzeCausality(event: FormEvent) {
    event.preventDefault();
    analyze.mutate({ target_service: targetService.trim() || undefined }, { onSuccess: (data) => setSelected(data.report) });
    analyzeRca.mutate({ target_service: targetService.trim() || undefined }, { onSuccess: (data) => setSelected(data.report) });
  }

  function generateReport() {
    if (!selected) return;
    report.mutate({ incident: selected, topology_impact: { root_service: selected.target_service } });
  }

  const latestRca = analyzeRca.data?.report ?? rcaReports.data?.reports?.[0];
  const active = report.data ?? selected ?? analyze.data?.report;

  return (
    <div className="page">
      <div className="page-heading"><div><h2>Causality</h2><p>Statistical precursor reports, ranked evidence, and conservative causality analysis.</p></div></div>
      <form className="form-grid two-column" onSubmit={analyzeCausality}>
        <div className="form-field"><label htmlFor="target-service">Target service</label><input id="target-service" value={targetService} onChange={(event) => setTargetService(event.target.value)} placeholder="optional service from topology" /></div>
        <button type="submit" className="full" disabled={analyze.isPending}>Analyze causality</button>
      </form>
      {analyze.error ? <div className="state error">{analyze.error.message}</div> : null}
      {analyzeRca.error ? <div className="state error">{analyzeRca.error.message}</div> : null}
      <div className="grid two">
        <StatusPanel title="Current RCA Summary" loading={analyzeRca.isPending || rcaReports.isLoading} error={rcaReports.error}>
          {latestRca ? <RcaReportPanel value={latestRca} /> : <div className="state">No RCA evidence bundle returned. Run analysis after telemetry and topology are available.</div>}
        </StatusPanel>
        <StatusPanel title="RCA Evidence" loading={analyzeRca.isPending || rcaReports.isLoading}>
          {latestRca ? <EvidenceReportPanel value={latestRca} /> : <div className="state">No evidence returned.</div>}
        </StatusPanel>
      </div>
      <StatusPanel title="RCA Bundles" loading={rcaReports.isLoading} error={rcaReports.error}>
        <DataTable
          caption="RCA evidence bundles"
          rows={rcaReports.data?.reports ?? []}
          empty="No RCA bundles returned."
          onRowClick={(row) => setSelected(row)}
          columns={[
            { key: "generated_at", label: "Generated", width: "150px" },
            { key: "report_id", label: "Report", width: "230px" },
            { key: "target_service", label: "Target", width: "140px" },
            { key: "likely_root_cause_service", label: "Likely root", width: "160px" },
            { key: "status", label: "Status", width: "140px" },
            { key: "confidence_score", label: "Confidence", width: "110px", render: (row) => <Badge tone="teal">{String(row.confidence_score ?? "insufficient data")}</Badge> },
            { key: "explanation", label: "Evidence-based explanation" },
          ]}
        />
      </StatusPanel>
      <StatusPanel title="Causal Reports" loading={reports.isLoading} error={reports.error}>
        <DataTable
          caption="Causal reports"
          rows={reports.data?.reports ?? []}
          empty="No data returned."
          onRowClick={(row) => setSelected(row)}
          columns={[
            { key: "generated_at", label: "Generated", width: "150px" },
            { key: "report_id", label: "Report", width: "230px" },
            { key: "target_service", label: "Target", width: "140px" },
            { key: "status", label: "Status", width: "140px" },
            { key: "confidence", label: "Confidence", width: "110px", render: (row) => <Badge tone="teal">{String(row.confidence ?? "No data returned.")}</Badge> },
            { key: "summary", label: "Ranked evidence summary" },
          ]}
        />
      </StatusPanel>
      <div className="quick-actions">
        <button type="button" className="btn-dry" disabled={!selected || report.isPending} onClick={generateReport}>Generate report template</button>
      </div>
      {report.error ? <div className="state error">{report.error.message}</div> : null}
      <div className="grid two">
        <StatusPanel title="Causal Report" loading={report.isPending}>
          {active ? <CausalReportPanel value={active} /> : <div className="state">No data returned.</div>}
        </StatusPanel>
        <BlastRadiusPanel service={String((active as Record<string, unknown> | undefined)?.target_service ?? "") || undefined} />
      </div>
      <StatusPanel title="Evidence" loading={false}>
        {active ? <EvidenceReportPanel value={active} /> : <div className="state">No data returned.</div>}
      </StatusPanel>
      {active ? <StatusPanel title="Raw Causal Payload"><JsonBlock value={active} /></StatusPanel> : null}
    </div>
  );
}
