from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Repository


def _fake_embeddings(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 384), dtype="float32")
    for idx, text in enumerate(texts):
        vectors[idx, len(text) % 384] = 1.0
    return vectors


def _fake_embedding(text: str) -> np.ndarray:
    vector = np.zeros(384, dtype="float32")
    vector[len(text) % 384] = 1.0
    return vector


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester@example.com",
            email="tester@example.com",
            password="test-password-123",
            first_name="Tester",
        )
        self.client.force_login(self.user)

    def _build_repo_zip(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "sample_repo/auth.py",
                "def login(user):\n    return user.is_authenticated\n",
            )
            archive.writestr(
                "sample_repo/views.py",
                "from auth import login\n\ndef handler(request):\n    return login(request.user)\n",
            )
        return buffer.getvalue()

    def test_upload_index_and_ask_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            uploads = Path(tmp_dir) / "uploads"
            indexes = Path(tmp_dir) / "indexes"
            with override_settings(UPLOAD_REPOS_DIR=uploads, VECTOR_INDEX_DIR=indexes):
                upload_file = SimpleUploadedFile(
                    "sample_repo.zip",
                    self._build_repo_zip(),
                    content_type="application/zip",
                )

                with patch(
                    "core.services.repository_service.generate_embeddings",
                    side_effect=_fake_embeddings,
                ):
                    upload_response = self.client.post("/api/upload/", {"repo": upload_file})

                self.assertEqual(upload_response.status_code, 200)
                upload_payload = upload_response.json()
                self.assertEqual(upload_payload["status"], "success")
                repository_id = upload_payload["repository"]["id"]
                repository = Repository.objects.get(id=repository_id)
                self.assertEqual(repository.status, Repository.Status.READY)
                self.assertEqual(repository.user_id, self.user.id)
                self.assertGreater(repository.total_chunks, 0)

                with patch(
                    "core.services.answer_service.generate_embedding",
                    side_effect=_fake_embedding,
                ):
                    ask_response = self.client.post(
                        "/api/ask/",
                        data=json.dumps(
                            {
                                "question": "Where is login implemented?",
                                "repository_id": repository_id,
                            }
                        ),
                        content_type="application/json",
                    )

                self.assertEqual(ask_response.status_code, 200)
                ask_payload = ask_response.json()
                self.assertEqual(ask_payload["status"], "success")
                self.assertIn("Direct answer", ask_payload["answer"])
                self.assertTrue(len(ask_payload["sources"]) > 0)
