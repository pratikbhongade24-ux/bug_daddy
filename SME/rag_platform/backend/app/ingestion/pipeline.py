import hashlib
from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ingestion.chunkers import code_chunk, semantic_chunk, resolve_document_type, discover_files
from app.ingestion.parsers import parse_file
from app.models.entities import EmbeddingChunk, IngestionJob, AuditLog
from app.services.bedrock import bedrock_client


def _metadata(path: str, doc_type: str) -> dict:
    p = Path(path)
    parts = p.parts
    service_name = 'shared'
    if 'customer_onboarding' in parts:
        service_name = 'customer_onboarding'
    elif 'kyc_service' in parts:
        service_name = 'kyc_service'
    elif 'loan_disbursement' in parts:
        service_name = 'loan_disbursement'
    elif 'repayment_service' in parts:
        service_name = 'repayment_service'

    return {
        'service_name': service_name,
        'module': p.parent.name,
        'api_name': p.stem,
        'repo': 'SME',
        'file_path': str(p),
        'table_name': None,
        'environment': settings.env,
        'application': settings.application_name,
        'version': settings.app_version,
        'document_type': doc_type,
    }


def ingest_repository(db: Session, root_path: str) -> dict:
    job = IngestionJob(source=root_path, status='RUNNING')
    db.add(job)
    db.commit()
    db.refresh(job)

    total_chunks = 0
    try:
        for file_path in discover_files(root_path):
            content, extra = parse_file(file_path)
            if not content.strip():
                continue

            doc_type = resolve_document_type(file_path)
            meta = _metadata(file_path, doc_type)
            meta.update(extra)

            chunks = code_chunk(content) if doc_type == 'code' else semantic_chunk(content)
            for idx, chunk in enumerate(chunks):
                emb = bedrock_client.embed(chunk)
                chunk_id = hashlib.sha1(f'{file_path}:{idx}:{chunk[:80]}'.encode('utf-8')).hexdigest()
                stmt = insert(EmbeddingChunk).values(
                    chunk_id=chunk_id,
                    content=chunk,
                    content_tsv=chunk,
                    embedding=emb,
                    meta_json=meta,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[EmbeddingChunk.chunk_id],
                    set_={
                        'content': chunk,
                        'content_tsv': chunk,
                        'embedding': emb,
                        'metadata': meta,
                    },
                )
                db.execute(stmt)
                total_chunks += 1

        job.status = 'COMPLETED'
        job.document_count = total_chunks
        job.completed_at = datetime.utcnow()
        db.add(AuditLog(action='ingestion', status='success', details={'source': root_path, 'chunks': total_chunks}))
        db.commit()
        return {'job_id': job.id, 'chunks': total_chunks}
    except Exception as exc:
        db.rollback()
        job.status = 'FAILED'
        job.error = str(exc)
        db.add(AuditLog(action='ingestion', status='failed', details={'source': root_path, 'error': str(exc)}))
        db.commit()
        raise
