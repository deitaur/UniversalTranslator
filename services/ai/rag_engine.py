"""
RAG (Retrieval-Augmented Generation) Engine.
Handles reading material files, tokenization, chunking, and TF-IDF semantic search.
"""

import re
import math
from collections import Counter
from pathlib import Path
from storage.roles import list_materials

def _read_file_text(filepath):
    """Read text content from a file. Tries UTF-8 first, then cp1251 (Russian Windows)."""
    p = Path(filepath)
    # Try UTF-8 first (most common modern encoding)
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        pass
    # Fallback to Windows-1251 (common for Russian text files)
    try:
        return p.read_text(encoding="cp1251")
    except Exception:
        pass
    # Last resort: UTF-8 with replacement characters
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _chunk_text(text, chunk_size=500, overlap=100):
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def _tokenize(text):
    """Simple word tokenization."""
    return re.findall(r"[a-zA-ZЀ-ӿ]{2,}", text.lower())


def _compute_tfidf(query_tokens, chunks_tokens):
    """Compute TF-IDF similarity between query and each chunk."""
    if not chunks_tokens:
        return []
    # IDF
    doc_count = len(chunks_tokens)
    df = Counter()
    for tokens in chunks_tokens:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    idf = {}
    for t in df:
        idf[t] = math.log((doc_count + 1) / (df[t] + 1)) + 1

    # Query TF-IDF vector
    query_tf = Counter(query_tokens)
    query_vec = {t: query_tf[t] * idf.get(t, 1) for t in query_tf}

    scores = []
    for chunk_tokens in chunks_tokens:
        chunk_tf = Counter(chunk_tokens)
        chunk_vec = {t: chunk_tf[t] * idf.get(t, 1) for t in chunk_tf}
        # Cosine similarity
        dot = sum(query_vec.get(t, 0) * chunk_vec.get(t, 0) for t in set(query_vec) | set(chunk_vec))
        norm_q = math.sqrt(sum(v * v for v in query_vec.values())) or 1
        norm_c = math.sqrt(sum(v * v for v in chunk_vec.values())) or 1
        scores.append(dot / (norm_q * norm_c))
    return scores


def search_materials(role_id, query, top_k=3, max_context_chars=4000):
    """Search role materials for relevant chunks using TF-IDF."""
    files = list_materials(role_id)
    if not files:
        return ""

    all_chunks = []
    for f in files:
        text = _read_file_text(f)
        if text.strip():
            chunks = _chunk_text(text)
            all_chunks.extend(chunks)

    if not all_chunks:
        return ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    chunks_tokens = [_tokenize(c) for c in all_chunks]
    scores = _compute_tfidf(query_tokens, chunks_tokens)

    # Get top-k chunks
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    result_parts = []
    total_len = 0
    for idx, score in ranked[:top_k]:
        if score < 0.05:
            break
        chunk = all_chunks[idx]
        if total_len + len(chunk) > max_context_chars:
            break
        result_parts.append(chunk)
        total_len += len(chunk)

    if not result_parts:
        return ""

    return "\n\n---\n\n".join(result_parts)
