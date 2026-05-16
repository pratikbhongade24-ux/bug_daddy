import re
from collections import defaultdict

from sqlalchemy import text, or_
from sqlalchemy.orm import Session

from rag.models.entities import EmbeddingChunk


def vector_search(db: Session, embedding: list[float], top_k: int = 12) -> list[dict]:
    emb_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    q = text("""
        SELECT id, chunk_id, content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
        FROM rag_embeddings
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)
    rows = db.execute(q, {"embedding": emb_literal, "top_k": top_k}).mappings().all()
    return [dict(r) for r in rows]


def keyword_search(db: Session, query: str, top_k: int = 12) -> list[dict]:
    terms = [t.strip() for t in re.split(r"[\s,.:;()\[\]{}]+", query) if len(t.strip()) > 2][:8]
    if not terms:
        return []
    filters = [EmbeddingChunk.content.ilike(f"%{t.replace('%', '')}%") for t in terms]
    rows = db.query(EmbeddingChunk).filter(or_(*filters)).limit(top_k).all()
    return [
        {"id": r.id, "chunk_id": r.chunk_id, "content": r.content, "metadata": r.meta_json, "score": 0.55}
        for r in rows
    ]


def _reciprocal_rank_fusion(rank_sets: list[list[dict]], rrf_k: int = 60) -> list[dict]:
    fused: dict[str, float] = defaultdict(float)
    exemplar: dict[str, dict] = {}
    for rows in rank_sets:
        for rank, row in enumerate(rows, start=1):
            cid = row["chunk_id"]
            fused[cid] += 1.0 / (rrf_k + rank)
            if cid not in exemplar or row.get("score", 0) > exemplar[cid].get("score", 0):
                exemplar[cid] = row
    merged = []
    for cid, score in fused.items():
        base = dict(exemplar[cid])
        base["score"] = score
        merged.append(base)
    return sorted(merged, key=lambda x: x["score"], reverse=True)


def hybrid_merge(vec_rows: list[dict], key_rows: list[dict], top_k: int = 10, rrf_k: int = 60) -> list[dict]:
    return _reciprocal_rank_fusion([vec_rows, key_rows], rrf_k=rrf_k)[:top_k]


def rerank(rows: list[dict], query: str) -> list[dict]:
    query_words = set(query.lower().split())
    for row in rows:
        overlap = len(query_words.intersection(set(row["content"].lower().split())))
        meta = row.get("metadata") or {}
        row["score"] = row["score"] + overlap * 0.01 + (0.02 if meta.get("service_name") else 0.0)
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def diversify_by_source(rows: list[dict], top_k: int, max_per_file: int = 3) -> list[dict]:
    selected: list[dict] = []
    per_file: dict[str, int] = defaultdict(int)
    for row in rows:
        key = (row.get("metadata") or {}).get("file_path") or row.get("chunk_id") or "unknown"
        if per_file[key] >= max_per_file:
            continue
        selected.append(row)
        per_file[key] += 1
        if len(selected) >= top_k:
            break
    return selected


def compress_context(rows: list[dict], max_chars: int = 7000) -> list[dict]:
    chunks = []
    used = 0
    for row in rows:
        c = row["content"]
        if used + len(c) > max_chars:
            break
        chunks.append(row)
        used += len(c)
    return chunks
