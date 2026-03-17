from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from django.conf import settings
from django.db import connection, transaction

from core.fields import serialize_vector
from core.models import RepositoryChunk

try:
    import faiss
except Exception:
    faiss = None


INDEX_FILENAME = "index.faiss"
METADATA_FILENAME = "metadata.json"
FALLBACK_VECTORS_FILENAME = "vectors.npy"
_INDEX_CACHE: dict[int, tuple[object, list[dict], np.ndarray | None]] = {}


def _vector_store_backend() -> str:
    configured = str(getattr(settings, "VECTOR_STORE_BACKEND", "auto")).strip().lower()
    if configured == "filesystem":
        return "filesystem"
    if configured == "database":
        return "database" if connection.vendor == "postgresql" else "filesystem"
    return "database" if connection.vendor == "postgresql" else "filesystem"


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _repo_index_dir(repository_id: int) -> Path:
    index_root = Path(settings.VECTOR_INDEX_DIR)
    index_root.mkdir(parents=True, exist_ok=True)
    repo_dir = index_root / f"repo_{repository_id}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


def _load_cached_index(repository_id: int) -> tuple[object, list[dict], np.ndarray | None]:
    if repository_id in _INDEX_CACHE:
        return _INDEX_CACHE[repository_id]

    repo_dir = _repo_index_dir(repository_id)
    index_path = repo_dir / INDEX_FILENAME
    metadata_path = repo_dir / METADATA_FILENAME
    vectors_path = repo_dir / FALLBACK_VECTORS_FILENAME

    if not metadata_path.exists():
        raise FileNotFoundError(f"No saved metadata found for repository {repository_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if faiss is not None and index_path.exists():
        index = faiss.read_index(str(index_path))
        _INDEX_CACHE[repository_id] = (index, metadata, None)
        return index, metadata, None

    if vectors_path.exists():
        vectors = np.load(vectors_path).astype("float32")
        _INDEX_CACHE[repository_id] = (None, metadata, vectors)
        return None, metadata, vectors

    raise FileNotFoundError(f"No saved index vectors found for repository {repository_id}")


def _store_filesystem_index(
    repository_id: int,
    vectors: np.ndarray,
    metadata: list[dict],
) -> str:
    if len(vectors) == 0:
        raise ValueError("Cannot build index with empty vectors")
    if len(vectors) != len(metadata):
        raise ValueError("Vector count and metadata count must match")

    vectors = np.asarray(vectors, dtype="float32")
    vectors = _normalize(vectors)

    repo_dir = _repo_index_dir(repository_id)
    index_path = repo_dir / INDEX_FILENAME
    metadata_path = repo_dir / METADATA_FILENAME
    vectors_path = repo_dir / FALLBACK_VECTORS_FILENAME

    if faiss is not None:
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(index_path))
        cached_index = index
        cached_vectors = None
    else:
        np.save(vectors_path, vectors)
        cached_index = None
        cached_vectors = vectors

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    _INDEX_CACHE[repository_id] = (cached_index, metadata, cached_vectors)
    return str(repo_dir)


def _store_database_index(
    repository_id: int,
    vectors: np.ndarray,
    metadata: list[dict],
) -> str:
    if len(vectors) == 0:
        raise ValueError("Cannot store empty vectors")
    if len(vectors) != len(metadata):
        raise ValueError("Vector count and metadata count must match")

    vectors = _normalize(np.asarray(vectors, dtype="float32"))
    table = connection.ops.quote_name(RepositoryChunk._meta.db_table)

    rows = []
    for vector, item in zip(vectors, metadata):
        rows.append(
            (
                repository_id,
                item.get("file", ""),
                item.get("path", item.get("file", "")),
                int(item.get("chunk_id", 0)),
                item.get("start_line"),
                item.get("end_line"),
                item.get("preview", ""),
                item.get("content", ""),
                serialize_vector(vector.tolist()),
            )
        )

    with transaction.atomic():
        RepositoryChunk.objects.filter(repository_id=repository_id).delete()
        with connection.cursor() as cursor:
            cursor.executemany(
                f"""
                INSERT INTO {table}
                (repository_id, file, path, chunk_id, start_line, end_line, preview, content, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, NOW())
                """,
                rows,
            )

    _INDEX_CACHE.pop(repository_id, None)
    return "database:pgvector"


def build_repository_index(
    repository_id: int,
    vectors: np.ndarray,
    metadata: list[dict],
) -> str:
    if _vector_store_backend() == "database":
        return _store_database_index(
            repository_id=repository_id,
            vectors=vectors,
            metadata=metadata,
        )
    return _store_filesystem_index(
        repository_id=repository_id,
        vectors=vectors,
        metadata=metadata,
    )


def _search_database(repository_id: int, query_vector: np.ndarray, k: int = 5) -> list[dict]:
    if not RepositoryChunk.objects.filter(repository_id=repository_id).exists():
        return []

    top_k = max(int(k), 1)
    query_literal = serialize_vector(_normalize(np.asarray([query_vector], dtype="float32"))[0].tolist())
    table = connection.ops.quote_name(RepositoryChunk._meta.db_table)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                file,
                path,
                chunk_id,
                start_line,
                end_line,
                preview,
                content,
                1 - (embedding <=> %s::vector) AS score
            FROM {table}
            WHERE repository_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [query_literal, repository_id, query_literal, top_k],
        )
        rows = cursor.fetchall()

    results: list[dict] = []
    for row in rows:
        results.append(
            {
                "file": row[0],
                "path": row[1],
                "chunk_id": row[2],
                "start_line": row[3],
                "end_line": row[4],
                "preview": row[5],
                "content": row[6],
                "score": float(row[7]),
            }
        )
    return results


def _search_filesystem(repository_id: int, query_vector: np.ndarray, k: int = 5) -> list[dict]:
    index, metadata, vectors = _load_cached_index(repository_id)

    if faiss is not None and index is not None:
        if index.ntotal == 0:
            return []
        top_k = min(max(k, 1), index.ntotal)
        query = np.asarray([query_vector], dtype="float32")
        faiss.normalize_L2(query)
        distances, indices = index.search(query, top_k)
    else:
        if vectors is None or len(vectors) == 0:
            return []
        top_k = min(max(k, 1), len(vectors))
        query = _normalize(np.asarray([query_vector], dtype="float32"))[0]
        scores = np.dot(vectors, query)
        indices = np.argsort(scores)[::-1][:top_k]
        distances = scores[indices]
        indices = np.asarray([indices])
        distances = np.asarray([distances])

    if len(metadata) == 0:
        return []

    results: list[dict] = []
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        item = dict(metadata[idx])
        item["score"] = float(score)
        results.append(item)

    return results


def search(repository_id: int, query_vector: np.ndarray, k: int = 5) -> list[dict]:
    if _vector_store_backend() == "database":
        results = _search_database(repository_id=repository_id, query_vector=query_vector, k=k)
        if results:
            return results

    return _search_filesystem(repository_id=repository_id, query_vector=query_vector, k=k)


def list_repository_files(repository_id: int) -> list[str]:
    if _vector_store_backend() == "database":
        files = list(
            RepositoryChunk.objects.filter(repository_id=repository_id)
            .order_by("path")
            .values_list("path", flat=True)
            .distinct()
        )
        if files:
            return files

    _, metadata, _ = _load_cached_index(repository_id)
    files = sorted({item.get("path", item.get("file", "")) for item in metadata if item})
    return [file for file in files if file]
