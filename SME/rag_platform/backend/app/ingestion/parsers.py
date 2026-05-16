import json
from pathlib import Path

import yaml
from docx import Document
from pypdf import PdfReader


def parse_file(path: str) -> tuple[str, dict]:
    p = Path(path)
    ext = p.suffix.lower()
    meta = {'file_name': p.name, 'file_path': str(p)}

    if ext in {'.md', '.py', '.sql', '.txt', '.toml', '.ini'}:
        return p.read_text(encoding='utf-8', errors='ignore'), meta

    if ext in {'.yaml', '.yml'}:
        raw = p.read_text(encoding='utf-8', errors='ignore')
        parsed = yaml.safe_load(raw)
        return yaml.safe_dump(parsed, sort_keys=False), meta

    if ext == '.json':
        raw = p.read_text(encoding='utf-8', errors='ignore')
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2), meta

    if ext == '.pdf':
        reader = PdfReader(str(p))
        text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        return text, meta

    if ext == '.docx':
        doc = Document(str(p))
        text = '\n'.join(par.text for par in doc.paragraphs)
        return text, meta

    return '', meta
