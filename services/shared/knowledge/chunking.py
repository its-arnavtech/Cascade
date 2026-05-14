from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from typing import Any

from .documents import KnowledgeDocument

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def chunk_document(document: KnowledgeDocument, chunk_size: int = 1000, overlap: int = 150) -> list[dict[str, Any]]:
    text = (document.raw_content or "").strip()
    if not text:
        return []
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size // 2))
    sections = _sections_with_headings(text)
    chunks: list[dict[str, Any]] = []
    index = 0
    for heading, body in sections:
        prefix = f"{heading}\n" if heading else ""
        section_text = (prefix + body.strip()).strip()
        start = 0
        while start < len(section_text):
            end = min(len(section_text), start + chunk_size)
            chunk_text = section_text[start:end].strip()
            if chunk_text:
                chunks.append(_chunk_row(document, chunk_text, index))
                index += 1
            if end >= len(section_text):
                break
            start = max(0, end - overlap)
    return chunks


def _sections_with_headings(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))
    return [(heading, "\n".join(lines)) for heading, lines in sections] or [("", text)]


def _chunk_row(document: KnowledgeDocument, chunk_text: str, index: int) -> dict[str, Any]:
    chunk_hash = hashlib.sha256(f"{document.content_hash}:{index}:{chunk_text}".encode("utf-8")).hexdigest()
    chunk_id = "chunk_" + hashlib.sha256(f"{document.document_id}:{index}:{chunk_hash}".encode("utf-8")).hexdigest()[:24]
    base = asdict(document)
    return {
        "chunk_id": chunk_id,
        "document_id": document.document_id,
        "chunk_index": index,
        "source_type": base["source_type"],
        "document_type": base["document_type"],
        "title": base["title"],
        "source_path": base["source_path"],
        "source_uri": base["source_uri"],
        "content_hash": base["content_hash"],
        "chunk_hash": chunk_hash,
        "phase": base["phase"],
        "service": base["service"],
        "namespace": base["namespace"],
        "severity": base["severity"],
        "tags": base["tags"],
        "metadata": base["metadata"],
        "chunk_text": chunk_text,
    }
