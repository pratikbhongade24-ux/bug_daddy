import json
from pathlib import Path

import yaml


def parse_file(path: str) -> tuple[str, dict]:
    p = Path(path)
    ext = p.suffix.lower()
    meta = {"file_name": p.name, "file_path": str(p)}

    if ext in {".md", ".py", ".sql", ".txt", ".toml", ".ini"}:
        return p.read_text(encoding="utf-8", errors="ignore"), meta

    if ext in {".yaml", ".yml"}:
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return yaml.safe_dump(yaml.safe_load(raw), sort_keys=False), meta

    if ext == ".json":
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return json.dumps(json.loads(raw), indent=2), meta

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in reader.pages), meta

    if ext == ".docx":
        from docx import Document
        doc = Document(str(p))
        return "\n".join(par.text for par in doc.paragraphs), meta

    return "", meta
