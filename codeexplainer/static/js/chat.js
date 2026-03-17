const state = {
  repositories: [],
  currentRepositoryId: null,
  currentFiles: [],
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  els.repoFile = document.getElementById("repoFile");
  els.uploadBtn = document.getElementById("uploadBtn");
  els.refreshRepos = document.getElementById("refreshRepos");
  els.uploadStatus = document.getElementById("uploadStatus");
  els.repoList = document.getElementById("repoList");
  els.repoCount = document.getElementById("repoCount");
  els.fileTree = document.getElementById("fileTree");
  els.fileFilter = document.getElementById("fileFilter");
  els.clearFileFilter = document.getElementById("clearFileFilter");
  els.fileCountBadge = document.getElementById("fileCountBadge");
  els.selectedRepoTitle = document.getElementById("selectedRepoTitle");
  els.selectedRepoMeta = document.getElementById("selectedRepoMeta");
  els.embeddingBackend = document.getElementById("embeddingBackend");
  els.chatRepoBadge = document.getElementById("chatRepoBadge");
  els.chatBox = document.getElementById("chatBox");
  els.questionInput = document.getElementById("questionInput");
  els.sendBtn = document.getElementById("sendBtn");
  els.promptChips = document.querySelectorAll(".prompt-chip");

  els.uploadBtn.addEventListener("click", uploadRepository);
  els.refreshRepos.addEventListener("click", () => loadRepositories(false));
  els.sendBtn.addEventListener("click", askQuestion);
  els.fileFilter.addEventListener("input", () => renderFileTree(state.currentFiles));
  els.clearFileFilter.addEventListener("click", clearFileFilter);

  els.questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      askQuestion();
    }
  });

  for (const chip of els.promptChips) {
    chip.addEventListener("click", () => {
      els.questionInput.value = chip.dataset.prompt || "";
      els.questionInput.focus();
    });
  }

  loadRepositories(true);
});

function setStatus(text, isError = false) {
  els.uploadStatus.textContent = text;
  els.uploadStatus.classList.toggle("error", isError);
}

function setEmbeddingBackend(backend) {
  els.embeddingBackend.textContent = `Embedding backend: ${backend || "-"}`;
}

function setFileCountBadge(visibleCount, totalCount = visibleCount) {
  const suffix = totalCount === 1 ? "file" : "files";
  if (visibleCount === totalCount) {
    els.fileCountBadge.textContent = `${totalCount} ${suffix} shown`;
    return;
  }
  els.fileCountBadge.textContent = `${visibleCount}/${totalCount} ${suffix}`;
}

function setSelectedRepositorySummary(repository) {
  if (!repository) {
    els.selectedRepoTitle.textContent = "No repository selected";
    els.selectedRepoMeta.textContent = "Select a repository card to inspect indexed files and narrow them quickly.";
    els.chatRepoBadge.textContent = "No repository selected";
    state.currentFiles = [];
    setFileCountBadge(0);
    return;
  }

  els.selectedRepoTitle.textContent = repository.name;
  els.selectedRepoMeta.textContent = `${capitalize(repository.status)} repository with ${Number(repository.total_files || 0)} indexed files and ${Number(repository.total_chunks || 0)} chunks.`;
  els.chatRepoBadge.textContent = shortName(repository.name, 32);
}

function shortName(value, maxLength = 38) {
  const name = String(value || "");
  if (name.length <= maxLength) {
    return name;
  }
  return `${name.slice(0, maxLength - 3)}...`;
}

function formatDate(isoDate) {
  if (!isoDate) {
    return "-";
  }
  try {
    return new Date(isoDate).toLocaleString();
  } catch {
    return isoDate;
  }
}

function normalizePath(path) {
  return String(path || "").replaceAll("\\", "/");
}

function clearFileFilter() {
  els.fileFilter.value = "";
  renderFileTree(state.currentFiles);
  els.fileFilter.focus();
}

function filteredPaths(paths) {
  const query = els.fileFilter.value.trim().toLowerCase();
  if (!query) {
    return paths.map((path) => normalizePath(path));
  }
  return paths
    .map((path) => normalizePath(path))
    .filter((path) => path.toLowerCase().includes(query));
}

async function loadRepositories(initialLoad = false) {
  try {
    const response = await fetch("/api/repositories/");
    const data = await response.json();
    state.repositories = data.repositories || [];
    renderRepositoryList();

    if (!state.repositories.length) {
      setSelectedRepositorySummary(null);
      els.fileTree.innerHTML = '<p class="empty">No repositories uploaded yet.</p>';
      return;
    }

    const currentStillExists = state.repositories.some((repo) => repo.id === state.currentRepositoryId);
    if (!state.currentRepositoryId || !currentStillExists) {
      await selectRepository(state.repositories[0].id);
      return;
    }

    if (!initialLoad) {
      renderRepositoryList();
    }
  } catch (error) {
    setStatus(`Failed to load repositories: ${error.message}`, true);
  }
}

function renderRepositoryList() {
  els.repoList.innerHTML = "";
  els.repoCount.textContent = String(state.repositories.length);

  if (!state.repositories.length) {
    els.repoList.innerHTML = '<p class="empty">No repositories uploaded yet.</p>';
    return;
  }

  for (const repo of state.repositories) {
    const status = String(repo.status || "processing").toLowerCase();
    const card = document.createElement("article");
    card.className = `repo-card ${repo.id === state.currentRepositoryId ? "active" : ""}`;

    const errorLine =
      status === "failed" && repo.error_message
        ? `<p class="repo-card-error">${escapeHtml(repo.error_message)}</p>`
        : "";

    card.innerHTML = `
      <div class="repo-card-head">
        <h3 class="repo-card-name" title="${escapeHtml(repo.name)}">${escapeHtml(shortName(repo.name, 46))}</h3>
        <span class="status-chip status-${escapeHtml(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="repo-card-meta">
        <span>${Number(repo.total_files || 0)} files</span>
        <span>${Number(repo.total_chunks || 0)} chunks</span>
      </div>
      <div class="repo-card-time">${escapeHtml(formatDate(repo.uploaded_at))}</div>
      ${errorLine}
      <button type="button" class="repo-card-open">Open workspace</button>
    `;

    card.addEventListener("click", () => selectRepository(repo.id));
    card.querySelector(".repo-card-open").addEventListener("click", (event) => {
      event.stopPropagation();
      selectRepository(repo.id);
    });

    els.repoList.appendChild(card);
  }
}

async function selectRepository(repositoryId) {
  state.currentRepositoryId = repositoryId;
  renderRepositoryList();

  const selected = state.repositories.find((repo) => repo.id === repositoryId);
  setSelectedRepositorySummary(selected);
  els.fileFilter.value = "";

  await loadRepositoryFiles(repositoryId);
}

async function loadRepositoryFiles(repositoryId) {
  try {
    const response = await fetch(`/api/repositories/${repositoryId}/files/`);
    const data = await response.json();

    if (data.status !== "success") {
      state.currentFiles = [];
      setFileCountBadge(0);
      els.fileTree.innerHTML = `<p class="empty">${escapeHtml(data.message || "Repository not ready yet.")}</p>`;
      return;
    }

    state.currentFiles = data.files || [];
    renderFileTree(state.currentFiles);
  } catch (error) {
    state.currentFiles = [];
    setFileCountBadge(0);
    els.fileTree.innerHTML = `<p class="empty">Failed to load files: ${escapeHtml(error.message)}</p>`;
  }
}

function renderFileTree(paths) {
  const visiblePaths = filteredPaths(paths);
  setFileCountBadge(visiblePaths.length, paths.length);

  if (!paths.length) {
    els.fileTree.innerHTML = '<p class="empty">No indexed files found.</p>';
    return;
  }

  if (!visiblePaths.length) {
    els.fileTree.innerHTML = '<p class="empty">No files match the current filter.</p>';
    return;
  }

  const rows = visiblePaths
    .map(
      (path) =>
        `<li class="file-row"><span class="file-dot"></span><code>${escapeHtml(path)}</code></li>`,
    )
    .join("");

  els.fileTree.innerHTML = `<ul class="file-list">${rows}</ul>`;
}

async function uploadRepository() {
  const file = els.repoFile.files[0];
  if (!file) {
    setStatus("Select a .zip repository file first.", true);
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    setStatus("Only .zip uploads are supported.", true);
    return;
  }

  setStatus("Uploading and indexing repository...");
  els.uploadBtn.disabled = true;

  const formData = new FormData();
  formData.append("repo", file);

  try {
    const response = await fetch("/api/upload/", {
       method: "POST",
       body: formData,
       credentials: "include",   // ⭐ THIS IS THE FIX
       headers: {
           "X-CSRFToken": getCookie("csrftoken"),
       },
      });
    const data = await response.json();

    if (data.status !== "success") {
      throw new Error(data.message || "Upload failed");
    }

    setEmbeddingBackend(data.embedding_backend);
    setStatus(
      `Indexed ${data.repository.name}: ${data.repository.total_files} files, ${data.repository.total_chunks} chunks.`,
    );

    await loadRepositories(false);
    await selectRepository(data.repository.id);
  } catch (error) {
    setStatus(`Upload failed: ${error.message}`, true);
  } finally {
    els.uploadBtn.disabled = false;
  }
}

async function askQuestion() {
  const question = els.questionInput.value.trim();
  if (!question) {
    return;
  }

  if (!state.currentRepositoryId) {
    appendMessage("bot", "Select a repository before asking a question.");
    return;
  }

  appendMessage("user", question);
  els.questionInput.value = "";
  els.sendBtn.disabled = true;

  try {
    const response = await fetch("/api/ask/", {
      method: "POST",
      credentials: "include",   // ⭐ ADD THIS
      headers: {
         "Content-Type": "application/json",
         "X-CSRFToken": getCookie("csrftoken"),
      },
  body: JSON.stringify({
        question,
        repository_id: state.currentRepositoryId,
        top_k: 6,
      }),
    });

    const data = await response.json();
    if (data.status !== "success") {
      throw new Error(data.message || "Question request failed");
    }

    setEmbeddingBackend(data.embedding_backend);
    appendMessage("bot", data.answer, data.sources || []);
  } catch (error) {
    appendMessage("bot", `Error: ${error.message}`);
  } finally {
    els.sendBtn.disabled = false;
    els.chatBox.scrollTop = els.chatBox.scrollHeight;
  }
}

function appendMessage(role, text, sources = []) {
  const block = document.createElement("div");
  block.className = `message ${role}`;
  block.innerHTML = `
    <div class="message-role">${role === "user" ? "You" : "Assistant"}</div>
    <div class="message-text">${toHtml(text)}</div>
  `;
  els.chatBox.appendChild(block);

  if (role === "bot" && sources.length) {
    const sourceWrap = document.createElement("div");
    sourceWrap.className = "sources-wrap";
    sourceWrap.innerHTML = renderSources(sources);
    els.chatBox.appendChild(sourceWrap);
  }
}

function renderSources(sources) {
  const rows = sources
    .map((source) => {
      const path = normalizePath(source.path || source.file || "unknown");
      const confidence = source.confidence || "Supporting";
      return `
        <li class="source-row">
          <div class="source-path">
            <code>${escapeHtml(path)}</code>
            ${lineRange(source)}
          </div>
          <span class="source-confidence ${confidenceClass(confidence)}">${escapeHtml(confidence)}</span>
        </li>
      `;
    })
    .join("");

  return `
    <details class="sources-disclosure">
      <summary>Evidence used (${sources.length})</summary>
      <ul class="source-list">${rows}</ul>
    </details>
  `;
}

function lineRange(source) {
  const start = Number(source.start_line || 0);
  const end = Number(source.end_line || 0);

  if (start && end) {
    return `<span class="source-lines">L${start}-${end}</span>`;
  }
  if (start) {
    return `<span class="source-lines">L${start}</span>`;
  }
  return "";
}

function confidenceClass(label) {
  const value = String(label || "").toLowerCase();
  if (value.includes("primary")) {
    return "confidence-primary";
  }
  if (value.includes("strong")) {
    return "confidence-strong";
  }
  return "confidence-supporting";
}

function toHtml(text) {
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function capitalize(value) {
  const text = String(value || "");
  if (!text) {
    return "";
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i += 1) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === `${name}=`) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
