param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ClearKnowledgeData
)

$ErrorActionPreference = "Stop"
function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }

Write-Section "Reset Cascade Knowledge and RAG"
kubectl config use-context "kind-$ClusterName" | Out-Null
kubectl -n $Namespace delete deployment knowledge-ingestion-service knowledge-retrieval-service --ignore-not-found=true
kubectl -n $Namespace delete service knowledge-ingestion-service knowledge-retrieval-service --ignore-not-found=true
kubectl -n $Namespace delete job clickhouse-schema-init qdrant-collection-init --ignore-not-found=true | Out-Null

if ($ClearKnowledgeData) {
    Write-Section "Clear Knowledge and RAG Tables And Knowledge Collection"
    $chPod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}'
    if ($chPod) {
        foreach ($table in @("knowledge_documents", "knowledge_chunks", "knowledge_ingestion_runs", "knowledge_queries")) {
            kubectl -n $Namespace exec $chPod -- clickhouse-client --query "TRUNCATE TABLE IF EXISTS cascade.$table"
            Assert-NativeSuccess "Truncate $table"
        }
    }
    $qPod = kubectl -n $Namespace get pod -l app=qdrant -o jsonpath='{.items[0].metadata.name}'
    if ($qPod) {
        kubectl -n $Namespace exec $qPod -- sh -c "wget -qO- --method=DELETE http://localhost:6333/collections/cascade_knowledge_base || true"
    }
}

& .\scripts\deploy-knowledge-rag.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipAnomalyDetectionDeploy
Assert-NativeSuccess "Redeploy Knowledge and RAG"
Write-Host "KNOWLEDGE RESET: PASS"
