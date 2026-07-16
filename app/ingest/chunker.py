"""Paragraph-aware chunking: ~1200 chars per chunk, 150-char overlap."""

CHUNK_SIZE = 1200
OVERLAP = 150


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            # try to break at a sentence/space boundary near the end
            for sep in (". ", "! ", "? ", " "):
                cut = text.rfind(sep, start + CHUNK_SIZE // 2, end)
                if cut != -1:
                    end = cut + 1
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return [c for c in chunks if c]
