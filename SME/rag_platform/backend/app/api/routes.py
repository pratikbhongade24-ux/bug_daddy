import json
import re
import time
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_api_key, require_admin_key
from app.db.database import get_db
from app.ingestion.pipeline import ingest_repository
from app.models.entities import Conversation, Message, Citation, Feedback, AuditLog
from app.models.schemas import ChatRequest, IngestRequest, ReindexRequest, FeedbackRequest
from app.retrieval.engine import (
    vector_search,
    keyword_search,
    hybrid_merge,
    rerank,
    diversify_by_source,
    compress_context,
)
from app.services.bedrock import bedrock_client
from app.services.rate_limit import check_rate_limit
from app.core.config import settings

router = APIRouter()


def _query_variants(question: str) -> list[str]:
    cleaned = re.sub(r'\s+', ' ', question).strip()
    variants = [cleaned]
    terms = [t for t in re.split(r'[\s,.:;()\[\]{}]+', cleaned.lower()) if len(t) > 3][:10]
    if terms:
        variants.append(' '.join(terms))
    return list(dict.fromkeys(v for v in variants if v))


def _normalize_answer_text(answer: str) -> str:
    text = (answer or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'(?m)^\s*#\s*#\s+', '## ', text)
    text = re.sub(r'(?m)^(\s*#{1,6}\s*[^\n:]+):\s*-\s*', r'\1:\n- ', text)
    text = re.sub(r'(?m)^(#{1,6})([A-Za-z])', r'\1 \2', text)
    text = re.sub(r'(?m)^###([A-Za-z])', r'### \1', text)
    text = re.sub(r'(?m)^##([A-Za-z])', r'## \1', text)
    repl = {
        'http://localhost:8001': 'Onboarding Service',
        'http://localhost:8002': 'KYC Service',
        'http://localhost:8003': 'Loan Disbursement Service',
        'http://localhost:8004': 'Repayment Service',
        'http://localhost:8005': 'Transaction Management Service',
        'http://localhost:8000': 'BugDaddy API',
        'http://localhost:3000': 'BugDaddy Dashboard',
        'localhost:8001': 'Onboarding Service',
        'localhost:8002': 'KYC Service',
        'localhost:8003': 'Loan Disbursement Service',
        'localhost:8004': 'Repayment Service',
        'localhost:8005': 'Transaction Management Service',
        'localhost:8000': 'BugDaddy API',
        'localhost:3000': 'BugDaddy Dashboard',
    }
    for old, new in repl.items():
        text = text.replace(old, new)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


@router.post('/ingest')
def ingest(payload: IngestRequest, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    check_rate_limit('ingest:global', limit=10, window_sec=60)
    return ingest_repository(db, payload.root_path)


@router.post('/admin/reindex')
def admin_reindex(payload: ReindexRequest, _: str = Depends(require_admin_key), db: Session = Depends(get_db)):
    check_rate_limit('reindex:admin', limit=3, window_sec=60)
    try:
        db.execute(text('TRUNCATE TABLE rag_citations RESTART IDENTITY'))
        db.execute(text('TRUNCATE TABLE rag_embeddings RESTART IDENTITY'))
        if payload.reset_conversations:
            db.execute(text('TRUNCATE TABLE rag_feedback RESTART IDENTITY CASCADE'))
            db.execute(text('TRUNCATE TABLE rag_messages RESTART IDENTITY CASCADE'))
            db.execute(text('TRUNCATE TABLE rag_conversations RESTART IDENTITY CASCADE'))
        db.commit()
    except Exception:
        db.rollback()
        raise

    result = ingest_repository(db, payload.root_path)
    return {
        'status': 'ok',
        'reindex': result,
        'root_path': payload.root_path,
        'reset_conversations': payload.reset_conversations,
    }


@router.post('/uploads')
def upload_docs(file: UploadFile = File(...), _: str = Depends(require_api_key)):
    return {'file_name': file.filename, 'status': 'received'}


@router.get('/conversations')
def list_conversations(
    external_user_id: str = Query(...),
    session_id: str | None = Query(default=None),
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    q = db.query(Conversation).filter(Conversation.external_user_id == external_user_id)
    if session_id:
        q = q.filter(Conversation.session_id == session_id)
    return q.order_by(Conversation.updated_at.desc()).all()


@router.post('/chat/stream')
def chat_stream(payload: ChatRequest, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
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
        vec_all.extend(vector_search(db, q_embedding, top_k=settings.retrieval_top_k_vector))
        key_all.extend(keyword_search(db, q, top_k=settings.retrieval_top_k_keyword))
    merged = hybrid_merge(
        vec_all,
        key_all,
        top_k=settings.retrieval_top_k_merged * 2,
        rrf_k=settings.retrieval_rrf_k,
    )

    if payload.filters:
        merged = [m for m in merged if all(m['metadata'].get(k) == v for k, v in payload.filters.items())]

    reranked = rerank(merged, payload.question)
    reranked = [row for row in reranked if float(row.get('score', 0.0)) >= settings.retrieval_min_score]
    reranked = diversify_by_source(
        reranked,
        top_k=settings.retrieval_top_k_merged,
        max_per_file=settings.retrieval_max_per_file,
    )
    compressed = compress_context(reranked, max_chars=settings.retrieval_context_chars)

    history_rows = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(settings.memory_messages).all()
    history_rows = list(reversed(history_rows))
    history = '\n'.join(f"{msg.role}: {msg.content}" for msg in history_rows if msg.content)

    context = '\n\n'.join(f"[source={row['metadata'].get('file_path')}]\n{row['content']}" for row in compressed)
    if settings.enable_grounded_fallback and not context.strip():
        answer = (
            "I don't have enough grounded context to answer confidently yet. "
            "Please ingest relevant docs or narrow your question by service/module."
        )
    else:
        prompt = (
            'You are an SME-grade assistant for banking loan platform engineering. '
            'Answer with concise reasoning, architecture traceability, and implementation clarity.\n\n'
            f'Conversation History:\n{history}\n\n'
            f'Question:\n{payload.question}\n\n'
            f'Retrieved Context:\n{context}\n\n'
            'Rules: Use only retrieved context for factual claims. '
            'If context is insufficient, explicitly say what is missing.\n'
            'Return: answer + bullet citations with file paths and relevance.'
        )
        answer = bedrock_client.generate(prompt)

    answer = _normalize_answer_text(answer)

    db.add(Message(conversation_id=conv.id, role='user', content=payload.question))
    db.flush()

    assistant_msg = Message(
        conversation_id=conv.id,
        role='assistant',
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
            chunk_id=row['chunk_id'],
            score=float(row['score']),
            source_name=row['metadata'].get('file_name', 'unknown'),
            file_path=row['metadata'].get('file_path'),
            meta_json=row['metadata'],
        ))

    conv.updated_at = datetime.utcnow()
    db.add(AuditLog(external_user_id=payload.external_user_id, action='chat', status='success', details={'conversation_id': conv.id}))
    db.commit()
    conversation_id = conv.id
    assistant_message_id = assistant_msg.id

    def stream():
        yield f"event: meta\ndata: {json.dumps({'conversation_id': conversation_id, 'message_id': assistant_message_id})}\n\n"
        for token in answer.split(' '):
            yield f"event: token\ndata: {json.dumps({'text': token + ' '})}\n\n"
        yield 'event: done\ndata: {}\n\n'

    return StreamingResponse(stream(), media_type='text/event-stream')


@router.get('/messages/{conversation_id}')
def messages(conversation_id: int, external_user_id: str = Query(...), _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.external_user_id == external_user_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail='Conversation not found')

    msgs = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.id.asc()).all()
    out = []
    for msg in msgs:
        cites = db.query(Citation).filter(Citation.message_id == msg.id).all()
        out.append({
            'id': msg.id,
            'role': msg.role,
            'content': msg.content,
            'citations': [{'score': c.score, 'source_name': c.source_name, 'file_path': c.file_path, 'metadata': c.meta_json} for c in cites],
        })
    return out


@router.post('/feedback')
def feedback(payload: FeedbackRequest, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    db.add(Feedback(message_id=payload.message_id, rating=payload.rating, comment=payload.comment))
    db.add(AuditLog(external_user_id=payload.external_user_id, action='feedback', status='success', details=payload.model_dump()))
    db.commit()
    return {'status': 'ok'}


@router.get('/metrics')
def metrics(_: str = Depends(require_api_key), db: Session = Depends(get_db)):
    msg_count = db.query(Message).count()
    avg_latency = db.query(Message).filter(Message.latency_ms.isnot(None)).all()
    lat = int(sum(m.latency_ms for m in avg_latency) / len(avg_latency)) if avg_latency else 0
    total_tokens = sum((m.tokens_in or 0) + (m.tokens_out or 0) for m in db.query(Message).all())
    return {
        'messages': msg_count,
        'avg_latency_ms': lat,
        'retrieval_accuracy_proxy': 'feedback-driven',
        'token_usage_proxy': total_tokens,
        'cost_proxy_usd': round(total_tokens / 1000000 * 3.2, 4),
        'failures': db.query(AuditLog).filter(AuditLog.status == 'failed').count(),
    }
