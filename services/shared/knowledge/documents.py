from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .metadata import infer_metadata


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    source_type: str
    document_type: str
    title: str
    source_path: str
    source_uri: str
    content_hash: str
    phase: str
    service: str
    namespace: str
    severity: str
    tags: list[str]
    metadata: dict[str, Any]
    raw_content: str


def document_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def stable_document_id(source_type: str, source_path: str, content_hash_value: str) -> str:
    seed = f"{source_type}:{source_path}:{content_hash_value}"
    return "doc_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def build_document(
    content: str,
    source_path: str,
    source_type: str = "repo_docs",
    source_uri: str = "",
    metadata: dict[str, Any] | None = None,
) -> KnowledgeDocument:
    metadata = metadata or {}
    inferred = infer_metadata(source_path, content, metadata)
    h = document_hash(content)
    return KnowledgeDocument(
        document_id=stable_document_id(source_type, source_path, h),
        source_type=source_type,
        document_type=inferred["document_type"],
        title=inferred["title"],
        source_path=source_path,
        source_uri=source_uri,
        content_hash=h,
        phase=inferred["phase"],
        service=inferred["service"],
        namespace=inferred["namespace"],
        severity=inferred["severity"],
        tags=inferred["tags"],
        metadata={**metadata, **inferred.get("metadata", {})},
        raw_content=content,
    )


def load_repo_documents(
    roots: list[str],
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    source_type: str = "repo_docs",
) -> list[KnowledgeDocument]:
    include_patterns = include_patterns or [".md", ".txt", ".json"]
    exclude_patterns = exclude_patterns or [".git", "__pycache__", "node_modules"]
    docs: list[KnowledgeDocument] = []
    for root in roots:
        path = Path(root)
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for candidate in sorted(candidates):
            normalized = str(candidate).replace("\\", "/")
            if any(pattern in normalized for pattern in exclude_patterns):
                continue
            if not _included(candidate, include_patterns):
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            if candidate.suffix.lower() == ".json":
                content = _normalize_json(content)
            if content.strip():
                docs.append(build_document(content, normalized, source_type=source_type))
    return docs


def _included(path: Path, patterns: list[str]) -> bool:
    suffix = path.suffix.lower()
    name = path.name.lower()
    for pattern in patterns:
        p = pattern.lower()
        if p.startswith("*.") and name.endswith(p[1:]):
            return True
        if p.startswith(".") and suffix == p:
            return True
        if p in name:
            return True
    return False


def _normalize_json(content: str) -> str:
    try:
        return json.dumps(json.loads(content), sort_keys=True, indent=2)
    except Exception:
        return content
