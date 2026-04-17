"""Embedding vector operations for semantic search."""
from __future__ import annotations

import numpy as np


def pack_vector(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Cosine similarity between a 1D query vector and an (N, D) candidate matrix."""
    q = query.astype(np.float32)
    m = candidates.astype(np.float32)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    denom = q_norm * m_norms
    denom = np.where(denom == 0, 1.0, denom)
    return (m @ q) / denom
