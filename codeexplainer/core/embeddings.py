from __future__ import annotations

import os
from functools import lru_cache

import numpy as np


EMBEDDING_DIMENSION = 384
MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

_fallback_vectorizer = None


@lru_cache(maxsize=1)
def _load_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(MODEL_NAME)
    except Exception:
        return None


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _fallback_encode(texts: list[str]) -> np.ndarray:
    global _fallback_vectorizer

    if _fallback_vectorizer is None:
        try:
            from sklearn.feature_extraction.text import HashingVectorizer

            _fallback_vectorizer = HashingVectorizer(
                n_features=EMBEDDING_DIMENSION,
                alternate_sign=False,
                norm="l2",
            )
        except Exception:
            _fallback_vectorizer = False

    if _fallback_vectorizer:
        vectors = _fallback_vectorizer.transform(texts).toarray().astype("float32")
        return _normalize(vectors)

    vectors = np.zeros((len(texts), EMBEDDING_DIMENSION), dtype="float32")
    for row, text in enumerate(texts):
        for token in text.split():
            vectors[row, hash(token) % EMBEDDING_DIMENSION] += 1.0
    return _normalize(vectors)


def generate_embeddings(texts: list[str] | tuple[str, ...]) -> np.ndarray:
    if not texts:
        return np.empty((0, EMBEDDING_DIMENSION), dtype="float32")

    model = _load_sentence_transformer()
    if model is not None:
        vectors = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")

    return _fallback_encode(list(texts))


def generate_embedding(text: str) -> np.ndarray:
    return generate_embeddings([text])[0]


def get_embedding_backend() -> str:
    return MODEL_NAME if _load_sentence_transformer() is not None else "hashing-fallback"
