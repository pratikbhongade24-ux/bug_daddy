-- Run once on the sonarqube postgres instance to enable the pgvector extension.
-- The RAG tables (rag_embeddings, rag_conversations, etc.) are created automatically
-- by SQLAlchemy on backend startup via init_db().
CREATE EXTENSION IF NOT EXISTS vector;
