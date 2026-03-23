var _mirrorWindowId = null;

window.addEventListener("pywebviewready", function () {
    refreshWindowList();
});

document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("url-input").addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            addUrl();
        }
    });
});

async function addUrl() {
    var input = document.getElementById("url-input");
    var url = input.value.trim();
    if (!url) return;

    var fullscreen = document.getElementById("fullscreen-check").checked;

    try {
        await pywebview.api.add_url(url, fullscreen);
        input.value = "";
        await refreshWindowList();
    } catch (err) {
        console.error("Failed to add URL:", err);
    }
}

async function closePage(windowId) {
    try {
        await pywebview.api.close_page(windowId);
        await refreshWindowList();
    } catch (err) {
        console.error("Failed to close page:", err);
    }
}

async function openMirrorModal(windowId) {
    _mirrorWindowId = windowId;
    try {
        var screens = await pywebview.api.get_screens();
        var list = document.getElementById("screen-list");
        list.innerHTML = "";

        screens.forEach(function (screen) {
            var btn = document.createElement("button");
            btn.className = "screen-btn";
            var label = screen.name + " (" + screen.width + "x" + screen.height + ")";
            if (screen.is_primary) label += " [Primary]";
            btn.textContent = label;
            btn.onclick = function () {
                mirrorToScreen(windowId, screen.index);
            };
            list.appendChild(btn);
        });

        document.getElementById("mirror-modal").classList.remove("hidden");
    } catch (err) {
        console.error("Failed to get screens:", err);
    }
}

function closeMirrorModal() {
    document.getElementById("mirror-modal").classList.add("hidden");
    _mirrorWindowId = null;
}

async function mirrorToScreen(windowId, screenIndex) {
    closeMirrorModal();
    try {
        await pywebview.api.mirror_page(windowId, screenIndex);
        await refreshWindowList();
    } catch (err) {
        console.error("Failed to mirror:", err);
    }
}

async function stopMirror(windowId) {
    try {
        await pywebview.api.stop_mirror(windowId);
        await refreshWindowList();
    } catch (err) {
        console.error("Failed to stop mirror:", err);
    }
}

async function refreshWindowList() {
    try {
        var pages = await pywebview.api.get_open_pages();
        var container = document.getElementById("windows-grid");
        container.innerHTML = "";

        if (!pages || pages.length === 0) {
            var msg = document.createElement("p");
            msg.className = "empty-msg";
            msg.id = "empty-msg";
            msg.textContent = "No windows open";
            container.appendChild(msg);
            return;
        }

        pages.forEach(function (page) {
            var card = document.createElement("div");
            card.className = "window-card";

            var closeBtn = document.createElement("button");
            closeBtn.className = "close-btn";
            closeBtn.textContent = "\u00d7";
            closeBtn.title = "Close";
            closeBtn.onclick = function () {
                closePage(page.id);
            };

            var domain = extractDomain(page.url);

            var favicon = document.createElement("img");
            favicon.className = "favicon";
            favicon.src = "https://www.google.com/s2/favicons?domain=" + domain + "&sz=64";
            favicon.alt = "";
            favicon.onerror = function () {
                this.style.display = "none";
            };

            var domainLabel = document.createElement("span");
            domainLabel.className = "domain";
            domainLabel.textContent = domain;

            // Mirror button
            var mirrorBtn = document.createElement("button");
            mirrorBtn.className = "mirror-btn";
            if (page.mirrored) {
                mirrorBtn.textContent = "Stop Mirror";
                mirrorBtn.classList.add("mirrored");
                mirrorBtn.onclick = function () {
                    stopMirror(page.id);
                };
            } else {
                mirrorBtn.textContent = "Mirror";
                mirrorBtn.onclick = function () {
                    openMirrorModal(page.id);
                };
            }

            card.appendChild(closeBtn);
            card.appendChild(favicon);
            card.appendChild(domainLabel);
            card.appendChild(mirrorBtn);
            container.appendChild(card);
        });
    } catch (err) {
        console.error("Failed to refresh:", err);
    }
}

function extractDomain(url) {
    try {
        var a = document.createElement("a");
        a.href = url;
        return a.hostname;
    } catch (e) {
        return url;
    }
}

function updateResourceStats(cpu, ram, gpu) {
    var cpuEl = document.getElementById("stat-cpu");
    var ramEl = document.getElementById("stat-ram");
    var gpuEl = document.getElementById("stat-gpu");

    if (cpuEl) cpuEl.textContent = "CPU: " + cpu + "%";
    if (ramEl) ramEl.textContent = "RAM: " + ram + " MB";
    if (gpuEl) gpuEl.textContent = gpu !== null ? "GPU: " + gpu + "%" : "GPU: N/A";
}
