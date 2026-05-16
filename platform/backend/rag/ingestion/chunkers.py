import os
import re
from pathlib import Path
from typing import Iterable


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


def code_chunk(content: str, max_lines: int = 90, overlap_lines: int = 12) -> list[str]:
    block_pattern = r"(?m)^(?:class|def|async\s+def)\s+[A-Za-z_][A-Za-z0-9_]*\s*\(?.*?:\s*$"
    starts = [m.start() for m in re.finditer(block_pattern, content)]
    if not starts:
        return _line_windows(content.splitlines(), max_lines=max_lines, overlap_lines=overlap_lines)

    starts.append(len(content))
    blocks = [content[starts[i]:starts[i + 1]].strip("\n") for i in range(len(starts) - 1) if content[starts[i]:starts[i + 1]].strip("\n")]
    chunks: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) <= max_lines:
            chunks.append(block)
        else:
            chunks.extend(_line_windows(lines, max_lines=max_lines, overlap_lines=overlap_lines))
    return chunks or _line_windows(content.splitlines(), max_lines=max_lines, overlap_lines=overlap_lines)


def resolve_document_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "code", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
        ".json": "config", ".sql": "sql", ".txt": "text", ".pdf": "pdf",
        ".docx": "docx", ".toml": "config", ".ini": "config",
    }.get(ext, "unknown")


def discover_files(root: str) -> Iterable[str]:
    allowed = {".py", ".md", ".yaml", ".yml", ".json", ".sql", ".txt", ".pdf", ".docx", ".toml", ".ini"}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in allowed:
                yield str(p)
