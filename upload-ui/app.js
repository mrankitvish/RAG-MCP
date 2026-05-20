document.addEventListener("DOMContentLoaded", () => {
    const context = window.SESSION_CONTEXT || {};
    const { sessionId, token } = context;

    if (!sessionId || !token) {
        showErrorInFeed("Session context missing. Please generate a new upload link.");
        return;
    }

    // UI elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const browseBtn = document.getElementById("browse-btn");
    const fileQueue = document.getElementById("file-queue");
    const queueContainer = document.getElementById("file-queue-container");
    const queueCount = document.getElementById("queue-count");
    const tagsInput = document.getElementById("tags-input");
    const uploadBtn = document.getElementById("upload-btn");
    const namespaceBadge = document.getElementById("namespace-badge");

    // Analytics counters
    const statTotal = document.getElementById("stat-total");
    const statSuccess = document.getElementById("stat-success");
    const statusFeed = document.getElementById("status-feed");

    let filesList = [];
    let processedTotal = 0;
    let processedSuccess = 0;

    // Fetch session details
    fetch(`/upload/${sessionId}/status?token=${token}`)
        .then(res => {
            if (!res.ok) throw new Error("Failed to validate upload session");
            return res.json();
        })
        .then(data => {
            namespaceBadge.textContent = data.namespace || "default";
            addFeedItem(`Session verified for namespace: <strong>${data.namespace}</strong>`, "info");
        })
        .catch(err => {
            namespaceBadge.textContent = "error";
            showErrorInFeed("Invalid or expired session. Please request a new link.");
            uploadBtn.disabled = true;
        });

    // Dropzone event handlers
    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    ["dragleave", "dragend"].forEach(event => {
        dropzone.addEventListener(event, () => {
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        handleFilesSelection(e.dataTransfer.files);
    });

    fileInput.addEventListener("change", (e) => {
        handleFilesSelection(e.target.files);
    });

    // Prevent propagation inside dropzone click for browsed button
    browseBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    function handleFilesSelection(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            // Check if already in queue
            if (filesList.some(f => f.name === file.name && f.size === file.size)) continue;
            filesList.push(file);
        }
        updateQueueUI();
    }

    function updateQueueUI() {
        fileQueue.innerHTML = "";
        if (filesList.length === 0) {
            queueContainer.classList.add("hidden");
            uploadBtn.disabled = true;
            return;
        }

        queueContainer.classList.remove("hidden");
        queueCount.textContent = filesList.length;
        uploadBtn.disabled = false;

        filesList.forEach((file, index) => {
            const sizeStr = formatBytes(file.size);
            const item = document.createElement("div");
            item.className = "file-item";
            item.innerHTML = `
                <div class="file-info">
                    <span class="file-name" title="${file.name}">${file.name}</span>
                    <span class="file-size">${sizeStr}</span>
                </div>
                <div class="file-actions">
                    <button class="btn-remove" data-index="${index}">&times;</button>
                </div>
            `;
            fileQueue.appendChild(item);
        });

        // Add remove click listener
        document.querySelectorAll(".btn-remove").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const index = parseInt(e.target.getAttribute("data-index"));
                filesList.splice(index, 1);
                updateQueueUI();
            });
        });
    }

    // Upload action
    uploadBtn.addEventListener("click", () => {
        if (filesList.length === 0) return;

        const spinner = uploadBtn.querySelector(".spinner");
        const btnText = uploadBtn.querySelector(".btn-text");

        uploadBtn.disabled = true;
        spinner.classList.remove("hidden");
        btnText.textContent = "Processing files through RAG Engine...";

        const formData = new FormData();
        filesList.forEach(file => {
            formData.append("files", file);
        });
        formData.append("tags", tagsInput.value);

        addFeedItem(`Uploading ${filesList.length} files to ingestion pipeline...`, "info");

        fetch(`/upload/${sessionId}?token=${token}`, {
            method: "POST",
            body: formData
        })
        .then(res => {
            if (!res.ok) throw new Error("Upload request failed");
            return res.json();
        })
        .then(data => {
            // Process results
            const results = data.results || [];
            results.forEach(res => {
                processedTotal++;
                if (res.status === "indexed") {
                    processedSuccess++;
                    addFeedItem(`Successfully indexed <strong>${res.filename}</strong> into vector store (${res.chunks} chunks).`, "success");
                } else {
                    addFeedItem(`Failed to ingest <strong>${res.filename}</strong>: ${res.error}`, "error");
                }
            });

            // Update stats
            statTotal.textContent = processedTotal;
            statSuccess.textContent = processedSuccess;

            // Clear queue
            filesList = [];
            updateQueueUI();
        })
        .catch(err => {
            showErrorInFeed(`Ingestion failed: ${err.message}`);
        })
        .finally(() => {
            spinner.classList.add("hidden");
            btnText.textContent = "Start Ingestion Pipeline";
        });
    });

    function addFeedItem(message, type = "info") {
        // Remove empty state placeholder
        const emptyPlaceholder = statusFeed.querySelector(".feed-empty");
        if (emptyPlaceholder) emptyPlaceholder.remove();

        const item = document.createElement("div");
        item.className = `feed-item feed-${type}`;
        item.innerHTML = `<span class="feed-time">[${new Date().toLocaleTimeString()}]</span> ${message}`;
        statusFeed.insertBefore(item, statusFeed.firstChild);
    }

    function showErrorInFeed(msg) {
        addFeedItem(msg, "error");
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
