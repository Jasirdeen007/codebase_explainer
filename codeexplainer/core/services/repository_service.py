from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from core.embeddings import generate_embeddings
from core.parser import extract_code_chunks
from core.vector_store import build_repository_index


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target_path = (destination / member.filename).resolve()
            if not str(target_path).startswith(str(destination.resolve())):
                raise ValueError("Unsafe ZIP path detected")
        archive.extractall(destination)


def _repository_folder_name(repo_name: str) -> str:
    stem = slugify(Path(repo_name).stem) or "repository"
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{stem}"


def save_uploaded_repository(uploaded_file) -> tuple[Path, Path]:
    upload_root = Path(settings.UPLOAD_REPOS_DIR)
    folder = upload_root / _repository_folder_name(uploaded_file.name)
    archive_dir = folder / "archive"
    extracted_dir = folder / "extracted"

    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / uploaded_file.name
    with zip_path.open("wb+") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)

    _safe_extract_zip(zip_path=zip_path, destination=extracted_dir)
    return folder, extracted_dir


def reset_repository_folder(path: str) -> None:
    folder = Path(path)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def index_repository(repository_id: int, extracted_path: str) -> dict:
    chunks = extract_code_chunks(
        extracted_path,
        max_file_bytes=int(getattr(settings, "MAX_CODE_FILE_BYTES", 1_000_000)),
    )
    if not chunks:
        raise ValueError("No supported source files were found in this repository")

    vectors = generate_embeddings([chunk["content"] for chunk in chunks])
    metadata = []
    for chunk in chunks:
        preview = chunk["content"][:450]
        metadata.append(
            {
                "file": chunk["file"],
                "path": chunk.get("path", chunk["file"]),
                "chunk_id": chunk.get("chunk_id", 0),
                "start_line": chunk.get("start_line"),
                "end_line": chunk.get("end_line"),
                "preview": preview,
                "content": chunk["content"],
            }
        )

    index_path = build_repository_index(
        repository_id=repository_id,
        vectors=vectors,
        metadata=metadata,
    )
    indexed_files = sorted({item["path"] for item in metadata})

    return {
        "index_path": index_path,
        "total_chunks": len(metadata),
        "total_files": len(indexed_files),
        "indexed_files": indexed_files,
    }
