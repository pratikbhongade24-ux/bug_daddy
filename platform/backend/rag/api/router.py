import json
import re
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from rag.core.config import (
    RAG_ADMIN_API_KEY,
    RETRIEVAL_TOP_K_VECTOR, RETRIEVAL_TOP_K_KEYWORD, RETRIEVAL_TOP_K_MERGED,
    RETRIEVAL_CONTEXT_CHARS, RETRIEVAL_RRF_K, RETRIEVAL_MIN_SCORE,
    RETRIEVAL_MAX_PER_FILE, MEMORY_MESSAGES, ENABLE_GROUNDED_FALLBACK,
)
from rag.db.database import get_db
from rag.ingestion.pipeline import ingest_repository
from rag.models.entities import Conversation, Message, Citation, Feedback, AuditLog
from rag.models.schemas import ChatRequest, IngestRequest, ReindexRequest, FeedbackRequest
from rag.retrieval.engine import (
    vector_search, keyword_search, hybrid_merge, rerank,
    diversify_by_source, compress_context,
)
from rag.services.bedrock import bedrock_client
from rag.services.rate_limit import check_rate_limit

router = APIRouter()


def _require_admin(x_admin_key: str | None = None):
    from fastapi import Header
    if not x_admin_key or x_admin_key != RAG_ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return x_admin_key


def _query_variants(question: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", question).strip()
    terms = [t for t in re.split(r"[\s,.:;()\[\]{}]+", cleaned.lower()) if len(t) > 3][:10]
    variants = [cleaned]
    if terms:
        variants.append(" ".join(terms))
    return list(dict.fromkeys(v for v in variants if v))


@router.post("/ingest")
def ingest(payload: IngestRequest, db: Session = Depends(get_db)):
    check_rate_limit("ingest:global", limit=10, window_sec=60)
    return ingest_repository(db, payload.root_path)


@router.post("/admin/reindex")
def admin_reindex(
    payload: ReindexRequest,
    x_admin_key: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _require_admin(x_admin_key)
    check_rate_limit("reindex:admin", limit=3, window_sec=60)
    try:
        db.execute(text("TRUNCATE TABLE rag_citations RESTART IDENTITY"))
        db.execute(text("TRUNCATE TABLE rag_embeddings RESTART IDENTITY"))
        if payload.reset_conversations:
            db.execute(text("TRUNCATE TABLE rag_feedback RESTART IDENTITY CASCADE"))
            db.execute(text("TRUNCATE TABLE rag_messages RESTART IDENTITY CASCADE"))
            db.execute(text("TRUNCATE TABLE rag_conversations RESTART IDENTITY CASCADE"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    result = ingest_repository(db, payload.root_path)
    return {"status": "ok", "reindex": result, "root_path": payload.root_path}


@router.post("/uploads")
def upload_docs(file: UploadFile = File(...)):
    return {"file_name": file.filename, "status": "received"}


@router.get("/conversations")
def list_conversations(
    external_user_id: str = Query(...),
    session_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Conversation).filter(Conversation.external_user_id == external_user_id)
    if session_id:
        q = q.filter(Conversation.session_id == session_id)
    return q.order_by(Conversation.updated_at.desc()).all()


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)):
    check_rate_limit(f"chat:{payload.external_user_id}:{payload.session_id}", limit=120, window_sec=60)
    start = time.time()

    conv = None
    if payload.conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == payload.conversation_id,
            Conversation.external_user_id == payload.external_user_id,
            Conversation.session_id == payload.session_id,
        ).first()
    if not conv:
        conv = Conversation(
            title=payload.question[:80],
            external_user_id=payload.external_user_id,
            session_id=payload.session_id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    queries = _query_variants(payload.question)
    vec_all: list[dict] = []
    key_all: list[dict] = []
    for q in queries:
        q_embedding = bedrock_client.embed(q)
        vec_all.extend(vector_search(db, q_embedding, top_k=RETRIEVAL_TOP_K_VECTOR))
        key_all.extend(keyword_search(db, q, top_k=RETRIEVAL_TOP_K_KEYWORD))

    merged = hybrid_merge(vec_all, key_all, top_k=RETRIEVAL_TOP_K_MERGED * 2, rrf_k=RETRIEVAL_RRF_K)
    if payload.filters:
        merged = [m for m in merged if all(m["metadata"].get(k) == v for k, v in payload.filters.items())]

    reranked = rerank(merged, payload.question)
    reranked = [r for r in reranked if float(r.get("score", 0.0)) >= RETRIEVAL_MIN_SCORE]
    reranked = diversify_by_source(reranked, top_k=RETRIEVAL_TOP_K_MERGED, max_per_file=RETRIEVAL_MAX_PER_FILE)
    compressed = compress_context(reranked, max_chars=RETRIEVAL_CONTEXT_CHARS)

    history_rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.id.desc())
        .limit(MEMORY_MESSAGES)
        .all()
    )
    history = "\n".join(f"{m.role}: {m.content}" for m in reversed(history_rows) if m.content)
    context = "\n\n".join(f"[source={r['metadata'].get('file_path')}]\n{r['content']}" for r in compressed)

    _is_casual = len(payload.question.split()) <= 6 and not any(
        kw in payload.question.lower()
        for kw in ("api", "service", "sql", "kyc", "loan", "disburse", "repay", "error", "flow", "schema", "table", "endpoint", "auth")
    )

    if ENABLE_GROUNDED_FALLBACK and not context.strip() and not _is_casual:
        answer = (
            "I don't have enough grounded context to answer that yet. "
            "Please ingest relevant docs or narrow your question by service or module."
        )
    else:
        prompt = (
            "You are an SME-grade assistant for a banking loan platform engineering team. "
            "You help engineers with incidents, API contracts, KYC flows, disbursement logic, and architecture decisions.\n"
            "For casual greetings or small talk, respond warmly and briefly, then offer to help with technical questions.\n\n"
            f"Conversation History:\n{history}\n\n"
            f"Question:\n{payload.question}\n\n"
            f"Retrieved Context:\n{context}\n\n"
            "Rules: Use retrieved context for factual claims. "
            "If context is insufficient for a technical question, say so explicitly.\n"
            "Return a concise answer. For technical questions include bullet citations with file paths."
        )
        answer = bedrock_client.generate(prompt)

    db.add(Message(conversation_id=conv.id, role="user", content=payload.question))
    db.flush()

    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        latency_ms=int((time.time() - start) * 1000),
        tokens_in=len(payload.question.split()),
        tokens_out=len(answer.split()),
    )
    db.add(assistant_msg)
    db.flush()

    for row in compressed[:8]:
        db.add(Citation(
            message_id=assistant_msg.id,
            chunk_id=row["chunk_id"],
            score=float(row["score"]),
            source_name=row["metadata"].get("file_name", "unknown"),
            file_path=row["metadata"].get("file_path"),
            meta_json=row["metadata"],
        ))

    conv.updated_at = datetime.utcnow()
    db.add(AuditLog(
        external_user_id=payload.external_user_id,
        action="chat",
        status="success",
        details={"conversation_id": conv.id},
    ))
    db.commit()

    conv_id = conv.id
    msg_id = assistant_msg.id

    def stream():
        yield f"event: meta\ndata: {json.dumps({'conversation_id': conv_id, 'message_id': msg_id})}\n\n"
        for token in answer.split(" "):
            yield f"event: token\ndata: {json.dumps({'text': token + ' '})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/messages/{conversation_id}")
def messages(
    conversation_id: int,
    external_user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.external_user_id == external_user_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.id.asc()).all()
    out = []
    for msg in msgs:
        cites = db.query(Citation).filter(Citation.message_id == msg.id).all()
        out.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "citations": [
                {"score": c.score, "source_name": c.source_name, "file_path": c.file_path, "metadata": c.meta_json}
                for c in cites
            ],
        })
    return out


@router.post("/feedback")
def feedback(payload: FeedbackRequest, db: Session = Depends(get_db)):
    db.add(Feedback(message_id=payload.message_id, rating=payload.rating, comment=payload.comment))
    db.add(AuditLog(
        external_user_id=payload.external_user_id,
        action="feedback",
        status="success",
        details=payload.model_dump(),
    ))
    db.commit()
    return {"status": "ok"}


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    msg_count = db.query(Message).count()
    latency_rows = db.query(Message).filter(Message.latency_ms.isnot(None)).all()
    avg_lat = int(sum(m.latency_ms for m in latency_rows) / len(latency_rows)) if latency_rows else 0
    total_tokens = sum((m.tokens_in or 0) + (m.tokens_out or 0) for m in db.query(Message).all())
    return {
        "messages": msg_count,
        "avg_latency_ms": avg_lat,
        "token_usage_proxy": total_tokens,
        "cost_proxy_usd": round(total_tokens / 1_000_000 * 3.2, 4),
        "failures": db.query(AuditLog).filter(AuditLog.status == "failed").count(),
    }
