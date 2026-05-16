from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Float, Index
from pgvector.sqlalchemy import Vector

from app.db.database import Base


class EmbeddingChunk(Base):
    __tablename__ = 'rag_embeddings'
    id = Column(Integer, primary_key=True)
    chunk_id = Column(String(80), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    content_tsv = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=False)
    meta_json = Column('metadata', JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index('ix_rag_embeddings_chunk_id', 'chunk_id'),)


class Conversation(Base):
    __tablename__ = 'rag_conversations'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, default='New Chat')
    external_user_id = Column(String(120), nullable=False)
    session_id = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Message(Base):
    __tablename__ = 'rag_messages'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('rag_conversations.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Citation(Base):
    __tablename__ = 'rag_citations'
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('rag_messages.id', ondelete='CASCADE'), nullable=False)
    chunk_id = Column(String(80), nullable=False)
    score = Column(Float, nullable=False)
    source_name = Column(String(255), nullable=False)
    file_path = Column(String(1000), nullable=True)
    meta_json = Column('metadata', JSON, nullable=False)


class Feedback(Base):
    __tablename__ = 'rag_feedback'
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('rag_messages.id', ondelete='CASCADE'), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = 'rag_audit_logs'
    id = Column(Integer, primary_key=True)
    external_user_id = Column(String(120), nullable=True)
    action = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IngestionJob(Base):
    __tablename__ = 'rag_ingestion_jobs'
    id = Column(Integer, primary_key=True)
    source = Column(String(120), nullable=False)
    status = Column(String(40), nullable=False, default='PENDING')
    document_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
