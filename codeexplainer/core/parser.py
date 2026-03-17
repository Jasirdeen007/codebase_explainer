from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rb",
    ".php",
    ".rs",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".md",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
    "env",
    "venv",
    ".venv",
}

DEFAULT_MAX_CHUNK_LINES = 80
DEFAULT_OVERLAP_LINES = 20
DEFAULT_MAX_FILE_BYTES = 1_000_000


def _is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _split_text_to_chunks(
    text: str,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[dict] = []
    step = max(1, max_chunk_lines - overlap_lines)
    index = 0
    chunk_id = 0

    while index < len(lines):
        start_line = index + 1
        end_line = min(index + max_chunk_lines, len(lines))
        chunk_lines = lines[index:end_line]
        content = "\n".join(chunk_lines).strip()
        if content:
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "content": content,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )
            chunk_id += 1
        if end_line >= len(lines):
            break
        index += step

    return chunks


def extract_code_chunks(
    repo_path: str | Path,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[dict]:
    root_path = Path(repo_path).resolve()
    chunks: list[dict] = []

    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        if ":Zone.Identifier" in file_path.name:
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in file_path.parts):
            continue
        if not _is_supported_file(file_path):
            continue
        if file_path.stat().st_size > max_file_bytes:
            continue

        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = file_path.read_text(encoding="latin-1")
            except Exception:
                continue
        except Exception:
            continue

        relative_path = str(file_path.relative_to(root_path)).replace("\\", "/")
        for piece in _split_text_to_chunks(
            text=text,
            max_chunk_lines=max_chunk_lines,
            overlap_lines=overlap_lines,
        ):
            chunks.append(
                {
                    "file": file_path.name,
                    "path": relative_path,
                    "chunk_id": piece["chunk_id"],
                    "start_line": piece["start_line"],
                    "end_line": piece["end_line"],
                    "content": piece["content"],
                }
            )

    return chunks
