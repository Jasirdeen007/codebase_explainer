from __future__ import annotations

import re
from collections import Counter, defaultdict

from core.embeddings import generate_embedding
from core.vector_store import search


STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "to",
    "of",
    "for",
    "in",
    "on",
    "with",
    "at",
    "this",
    "that",
    "it",
    "as",
    "by",
    "from",
    "or",
    "about",
    "what",
    "which",
    "where",
    "how",
    "explain",
    "show",
    "me",
}

LOGIC_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php", ".rs", ".cs", ".cpp", ".c"}
STYLING_EXTENSIONS = {".css", ".scss"}
STRUCTURE_EXTENSIONS = {".html", ".md", ".json", ".yml", ".yaml"}

AUTH_TERMS = {"auth", "authentication", "login", "signin", "token", "jwt", "oauth", "session", "password"}
DATA_TERMS = {"database", "model", "schema", "sql", "table", "migration", "orm"}


def _normalize_path(path: str | None) -> str:
    return (path or "").replace("\\", "/").strip()


def _file_extension(path: str) -> str:
    normalized = _normalize_path(path)
    if "." not in normalized:
        return ""
    return f".{normalized.rsplit('.', 1)[1].lower()}"


def _tokenize(text: str) -> list[str]:
    parts = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [token for token in parts if len(token) > 2 and token not in STOPWORDS]


def _intent(question: str) -> str:
    q = question.lower()
    if any(word in q for word in {"css", "style", "ui", "layout", "color", "theme", "design"}):
        return "styling"
    if any(word in q for word in {"flow", "logic", "function", "handler", "implement", "authentication", "api"}):
        return "logic"
    if any(word in q for word in {"file", "filename", "which file", "where is"}):
        return "lookup"
    return "general"


def _type_bonus(intent: str, extension: str) -> float:
    if intent == "styling":
        if extension in STYLING_EXTENSIONS:
            return 0.22
        if extension in STRUCTURE_EXTENSIONS:
            return 0.08
        return -0.05
    if intent == "logic":
        if extension in LOGIC_EXTENSIONS:
            return 0.20
        if extension in STRUCTURE_EXTENSIONS:
            return 0.05
        if extension in STYLING_EXTENSIONS:
            return -0.10
    return 0.0


def _keyword_matches(tokens: list[str], item: dict) -> tuple[int, list[str]]:
    haystack = " ".join(
        [
            _normalize_path(item.get("path") or item.get("file") or ""),
            (item.get("content") or ""),
            (item.get("preview") or ""),
        ]
    ).lower()
    matched = [token for token in tokens if token in haystack]
    return len(matched), matched[:6]


def _normalize_score(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value


def _rerank(question: str, results: list[dict]) -> list[dict]:
    if not results:
        return []

    tokens = _tokenize(question)
    detected_intent = _intent(question)

    semantic_scores = [max(0.0, float(item.get("score", 0.0))) for item in results]
    max_semantic = max(semantic_scores) if semantic_scores else 1.0

    lexical_counts = []
    matches_by_index: dict[int, list[str]] = {}
    for idx, item in enumerate(results):
        count, matched = _keyword_matches(tokens, item)
        lexical_counts.append(float(count))
        matches_by_index[idx] = matched

    max_lexical = max(lexical_counts) if lexical_counts else 1.0

    rescored: list[dict] = []
    for idx, item in enumerate(results):
        path = _normalize_path(item.get("path") or item.get("file") or "unknown")
        ext = _file_extension(path)
        semantic_norm = _normalize_score(semantic_scores[idx], max_semantic)
        lexical_norm = _normalize_score(lexical_counts[idx], max_lexical)
        combined = (semantic_norm * 0.60) + (lexical_norm * 0.34) + _type_bonus(detected_intent, ext)

        updated = dict(item)
        updated["path"] = path
        updated["_semantic_norm"] = semantic_norm
        updated["_lexical_norm"] = lexical_norm
        updated["_combined"] = combined
        updated["_matched_terms"] = matches_by_index[idx]
        rescored.append(updated)

    rescored.sort(key=lambda item: float(item["_combined"]), reverse=True)
    return rescored


def _summarize_repo_type(results: list[dict]) -> str:
    extensions = [_file_extension(item.get("path") or item.get("file") or "") for item in results]
    counter = Counter(ext for ext in extensions if ext)
    top = [ext for ext, _ in counter.most_common(3)]
    if not top:
        return "mixed repository"
    if top == [".css", ".html", ".js"] or ".html" in top and ".css" in top and ".js" in top:
        return "frontend repository (HTML/CSS/JS)"
    return "repository containing " + ", ".join(top)


def _is_missing_topic(question: str, results: list[dict]) -> bool:
    question_tokens = set(_tokenize(question))
    if not question_tokens:
        return False

    high_priority = set()
    if question_tokens & AUTH_TERMS:
        high_priority |= AUTH_TERMS
    if question_tokens & DATA_TERMS:
        high_priority |= DATA_TERMS
    if not high_priority:
        return False

    aggregate_matches = set()
    for item in results[:8]:
        aggregate_matches.update(item.get("_matched_terms", []))

    return not bool(aggregate_matches & high_priority)


def _confidence(item: dict, top_combined: float) -> str:
    if top_combined <= 0:
        return "Supporting"
    ratio = float(item.get("_combined", 0.0)) / top_combined
    if ratio >= 0.95:
        return "Primary"
    if ratio >= 0.82:
        return "Strong"
    return "Supporting"


def retrieve_context(repository_id: int, question: str, top_k: int = 6) -> list[dict]:
    query_vector = generate_embedding(question)
    candidate_count = max(14, top_k * 4)
    raw = search(repository_id=repository_id, query_vector=query_vector, k=candidate_count)
    ranked = _rerank(question=question, results=raw)
    return ranked[: max(4, top_k)]


def format_sources(results: list[dict]) -> list[dict]:
    if not results:
        return []

    unique: list[dict] = []
    seen = set()
    for item in results:
        key = (item.get("path"), item.get("start_line"), item.get("end_line"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    top_combined = max(float(item.get("_combined", 0.0)) for item in unique) if unique else 0.0
    sources: list[dict] = []
    for item in unique:
        preview = " ".join((item.get("preview") or item.get("content") or "").split())
        if len(preview) > 210:
            preview = f"{preview[:207]}..."
        sources.append(
            {
                "file": item.get("file"),
                "path": _normalize_path(item.get("path") or item.get("file")),
                "confidence": _confidence(item, top_combined),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
                "preview": preview,
            }
        )
    return sources


def _try_llm_answer(question: str, results: list[dict]) -> str | None:
    try:
        from core.services.llm_service import generate_reasoned_answer
    except Exception:
        return None
    try:
        return generate_reasoned_answer(question=question, results=results[:6])
    except Exception:
        return None


def build_answer(question: str, results: list[dict]) -> str:
    if not results:
        return (
            "I could not find relevant code for that question.\n"
            "Try asking with concrete terms like module names, function names, or file types."
        )

    if _is_missing_topic(question, results):
        repo_summary = _summarize_repo_type(results)
        return (
            f"I could not find explicit `{question}` logic in the indexed files.\n"
            f"This looks like a {repo_summary}, so that feature may not exist in this repository."
        )

    llm_answer = _try_llm_answer(question=question, results=results)
    if llm_answer:
        return llm_answer

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in results:
        grouped[_normalize_path(item.get("path") or item.get("file") or "unknown")].append(item)

    ranked_files = sorted(
        grouped.items(),
        key=lambda pair: max(float(chunk.get("_combined", 0.0)) for chunk in pair[1]),
        reverse=True,
    )
    top_file = ranked_files[0][0]

    lines = [f"Direct answer: start with `{top_file}`."]
    if len(ranked_files) > 1:
        lines.append(f"Then review `{ranked_files[1][0]}` for supporting logic.")

    lines.append("")
    lines.append("Why this answer:")
    for path, chunks in ranked_files[:3]:
        best = sorted(chunks, key=lambda item: float(item.get("_combined", 0.0)), reverse=True)[0]
        start = best.get("start_line")
        end = best.get("end_line")
        line_info = f" (lines {start}-{end})" if start and end else ""
        preview = " ".join((best.get("preview") or best.get("content") or "").split())
        if len(preview) > 180:
            preview = f"{preview[:177]}..."
        lines.append(f"- `{path}`{line_info}: {preview}")

    lines.append("")
    lines.append(f"Next step: open `{top_file}` first.")
    return "\n".join(lines)
