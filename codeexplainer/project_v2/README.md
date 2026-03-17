# Codebase Explainer V2 Workspace

This directory documents the upgraded architecture now implemented in the main Django app:

- repository-aware upload and indexing workflow
- persistent FAISS index files per repository
- chunked code parsing with metadata
- retrieval-backed answer API with source attribution
- GitHub + Claude-style web workspace UI

Core implementation files live in:

- `core/services/repository_service.py`
- `core/services/answer_service.py`
- `core/parser.py`
- `core/embeddings.py`
- `core/vector_store.py`
- `core/views.py`

Index files are stored under `vector_indexes/repo_<id>/`.
