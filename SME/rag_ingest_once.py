#!/usr/bin/env python3
"""
One-shot RAG ingestion script.

Steps:
  1. Create S3 bucket  sme-rag-documents  (ap-south-1) if it doesn't exist
  2. Upload every file from SME/docs/ into s3://sme-rag-documents/docs/
  3. Download each file from S3, chunk it, embed via Bedrock Titan,
     and upsert into the rag_embeddings table in the RDS Postgres instance.

Usage:
    python SME/rag_ingest_once.py

Requirements (install once):
    pip install boto3 psycopg2-binary pgvector sqlalchemy tenacity
"""

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import execute_values
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Configuration – all sourced from env or hardcoded defaults matching deploy.sh
# ---------------------------------------------------------------------------

AWS_REGION     = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET      = os.getenv("S3_BUCKET", "sme-rag-documents")
S3_PREFIX      = "docs/"

DATABASE_URL   = os.environ["RAG_DATABASE_URL"]

EMBEDDING_MODEL = os.getenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
DOCS_DIR        = Path(__file__).parent / "docs"

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

AWS_PROFILE = os.getenv("AWS_PROFILE")
if AWS_PROFILE is not None and not AWS_PROFILE.strip():
    AWS_PROFILE = None
if AWS_PROFILE is None:
    available_profiles = boto3.Session(region_name=AWS_REGION).available_profiles
    if "bug-daddy" in available_profiles:
        AWS_PROFILE = "bug-daddy"

_session_kwargs: dict = {"region_name": AWS_REGION}
if AWS_PROFILE:
    _session_kwargs["profile_name"] = AWS_PROFILE
session  = boto3.Session(**_session_kwargs)
s3       = session.client("s3")
bedrock  = session.client("bedrock-runtime", region_name=AWS_REGION)

# ---------------------------------------------------------------------------
# Step 1 – create S3 bucket
# ---------------------------------------------------------------------------

def ensure_bucket() -> None:
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        print(f"[s3] bucket '{S3_BUCKET}' already exists")
    except s3.exceptions.ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"403", "AccessDenied"}:
            print(f"[s3] bucket '{S3_BUCKET}' exists but HeadBucket is not permitted; continuing")
            return
        print(f"[s3] creating bucket '{S3_BUCKET}' in {AWS_REGION}...")
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=S3_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        s3.put_public_access_block(
            Bucket=S3_BUCKET,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        print(f"[s3] bucket created")


# ---------------------------------------------------------------------------
# Step 2 – upload docs
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json", ".sql", ".txt",
                      ".pdf", ".docx", ".toml", ".ini"}


def upload_docs() -> list[str]:
    """Upload files from DOCS_DIR to S3 and return list of S3 keys."""
    keys: list[str] = []
    for fpath in sorted(DOCS_DIR.rglob("*")):
        if fpath.is_dir():
            continue
        if fpath.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        relative = fpath.relative_to(DOCS_DIR)
        key = S3_PREFIX + str(relative)
        print(f"[s3] uploading {fpath.name}  →  s3://{S3_BUCKET}/{key}")
        s3.upload_file(str(fpath), S3_BUCKET, key)
        keys.append(key)
    print(f"[s3] {len(keys)} file(s) uploaded")
    return keys


def list_s3_docs() -> list[str]:
    """Return existing document keys from S3 when local docs are unavailable."""
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith("/"):
                continue
            if Path(key).suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            keys.append(key)
    keys.sort()
    print(f"[s3] found {len(keys)} existing document(s) under s3://{S3_BUCKET}/{S3_PREFIX}")
    return keys


# ---------------------------------------------------------------------------
# Chunking (mirrors SME/rag_platform chunkers.py)
# ---------------------------------------------------------------------------

def semantic_chunk(text: str, max_chars: int = 1800, overlap: int = 250) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            tail = buf[-overlap:] if buf else ""
            buf = f"{tail}\n{p}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def _line_windows(lines: list[str], max_lines: int = 90, overlap_lines: int = 12) -> list[str]:
    chunks: list[str] = []
    start = 0
    n = len(lines)
    while start < n:
        end = min(start + max_lines, n)
        chunks.append("\n".join(lines[start:end]))
        if end >= n:
            break
        start = max(end - overlap_lines, start + 1)
    return chunks


def code_chunk(content: str) -> list[str]:
    block_pattern = r"(?m)^(?:class|def|async\s+def)\s+[A-Za-z_][A-Za-z0-9_]*\s*\(?.*?:\s*$"
    starts = [m.start() for m in re.finditer(block_pattern, content)]
    if not starts:
        return _line_windows(content.splitlines())
    starts.append(len(content))
    blocks = [content[starts[i]:starts[i + 1]].strip("\n") for i in range(len(starts) - 1) if content[starts[i]:starts[i + 1]].strip("\n")]
    chunks: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        chunks.extend([block] if len(lines) <= 90 else _line_windows(lines))
    return chunks or _line_windows(content.splitlines())


DOC_TYPE_MAP = {
    ".py": "code", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".json": "config", ".sql": "sql", ".txt": "text", ".pdf": "pdf",
    ".docx": "docx", ".toml": "config", ".ini": "config",
}


def resolve_doc_type(path: str) -> str:
    return DOC_TYPE_MAP.get(Path(path).suffix.lower(), "unknown")


def parse_content(local_path: str) -> str:
    suffix = Path(local_path).suffix.lower()
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(local_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            print("[warn] pypdf not installed, skipping PDF")
            return ""
    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(local_path)
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            print("[warn] python-docx not installed, skipping DOCX")
            return ""
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
            with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                return yaml.dump(yaml.safe_load(f))
        except Exception:
            pass
    if suffix == ".json":
        with open(local_path, "r", encoding="utf-8", errors="replace") as f:
            try:
                return json.dumps(json.load(f), indent=2)
            except Exception:
                return f.read()
    with open(local_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Bedrock embedding
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def embed(text: str) -> list[float]:
    resp = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]


# ---------------------------------------------------------------------------
# Step 3 – ingest into Postgres
# ---------------------------------------------------------------------------

def run_schema(conn) -> None:
    """Ensure pgvector extension and rag_embeddings table exist."""
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rag_embeddings (
                id BIGSERIAL PRIMARY KEY,
                chunk_id VARCHAR(80) UNIQUE NOT NULL,
                content TEXT NOT NULL,
                content_tsv TEXT,
                embedding vector(1024) NOT NULL,
                metadata JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rag_ingestion_jobs (
                id BIGSERIAL PRIMARY KEY,
                source VARCHAR(120) NOT NULL,
                status VARCHAR(40) NOT NULL DEFAULT 'PENDING',
                document_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ
            );
        """)
        conn.commit()
    print("[db] schema ready")


UPSERT_SQL = """
INSERT INTO rag_embeddings (chunk_id, content, content_tsv, embedding, metadata, created_at)
VALUES %s
ON CONFLICT (chunk_id) DO UPDATE SET
    content      = EXCLUDED.content,
    content_tsv  = EXCLUDED.content_tsv,
    embedding    = EXCLUDED.embedding,
    metadata     = EXCLUDED.metadata;
"""


def ingest_keys(keys: list[str]) -> None:
    conn = psycopg2.connect(DATABASE_URL)
    run_schema(conn)

    total_chunks = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_ingestion_jobs (source, status, document_count, created_at)
            VALUES (%s, 'RUNNING', 0, %s)
            RETURNING id
            """,
            (f"s3://{S3_BUCKET}/{S3_PREFIX}", datetime.utcnow()),
        )
        job_id = cur.fetchone()[0]
        conn.commit()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for key in keys:
                filename = Path(key).name
                local_path = os.path.join(tmpdir, filename)
                print(f"[ingest] downloading s3://{S3_BUCKET}/{key}  →  {filename}")
                s3.download_file(S3_BUCKET, key, local_path)

                content = parse_content(local_path)
                if not content.strip():
                    print(f"[ingest] {filename}: empty, skipping")
                    continue

                doc_type = resolve_doc_type(local_path)
                meta = {
                    "service_name": "shared",
                    "module": "docs",
                    "api_name": Path(filename).stem,
                    "repo": "SME",
                    "file_path": key,
                    "environment": "production",
                    "application": "bank-loan-production-platform",
                    "version": "1.0.0",
                    "document_type": doc_type,
                    "s3_bucket": S3_BUCKET,
                    "s3_key": key,
                }

                chunks = code_chunk(content) if doc_type == "code" else semantic_chunk(content)
                rows = []
                for idx, chunk in enumerate(chunks):
                    chunk_id = hashlib.sha1(f"{key}:{idx}:{chunk[:80]}".encode()).hexdigest()
                    emb = embed(chunk)
                    rows.append((chunk_id, chunk, chunk, json.dumps(emb), json.dumps(meta), datetime.utcnow()))

                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        """
                        INSERT INTO rag_embeddings (chunk_id, content, content_tsv, embedding, metadata, created_at)
                        VALUES %s
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content     = EXCLUDED.content,
                            content_tsv = EXCLUDED.content_tsv,
                            embedding   = EXCLUDED.embedding,
                            metadata    = EXCLUDED.metadata
                        """,
                        rows,
                    )
                conn.commit()
                total_chunks += len(rows)
                print(f"[ingest] {filename}: {len(chunks)} chunk(s) embedded and upserted")

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rag_ingestion_jobs SET status='COMPLETED', document_count=%s, completed_at=%s WHERE id=%s",
                (total_chunks, datetime.utcnow(), job_id),
            )
            conn.commit()

        print(f"\n[done] {len(keys)} document(s) → {total_chunks} chunk(s) inserted into rag_embeddings")

    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rag_ingestion_jobs SET status='FAILED', error=%s WHERE id=%s",
                (str(exc), job_id),
            )
            conn.commit()
        conn.close()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"=== RAG One-Time Ingestion ===")
    print(f"Docs dir : {DOCS_DIR}")
    print(f"S3 bucket: s3://{S3_BUCKET}/{S3_PREFIX}")
    print(f"Database : {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    print(f"Model    : {EMBEDDING_MODEL}")
    print()

    ensure_bucket()
    if DOCS_DIR.exists():
        keys = upload_docs()
    else:
        print(f"[s3] local docs directory not found, using documents already in S3: {DOCS_DIR}")
        keys = list_s3_docs()

    if not keys:
        print("[warn] no files found to ingest")
        sys.exit(0)

    ingest_keys(keys)
