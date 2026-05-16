from app.ingestion.chunkers import semantic_chunk, code_chunk


def test_semantic_chunk_splits_long_text():
    text = ('A paragraph.\n\n' * 400)
    chunks = semantic_chunk(text, max_chars=500)
    assert len(chunks) > 1


def test_code_chunk_splits_by_lines():
    code = '\n'.join([f'line {i}' for i in range(220)])
    chunks = code_chunk(code, max_lines=90)
    assert len(chunks) == 3
