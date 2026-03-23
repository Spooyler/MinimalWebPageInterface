var _mirrorCallback = null;
var _presetsEditMode = false;

window.addEventListener("pywebviewready", function () {
    applyTheme();
    applyOptions();
    restoreCollapsedSections();
    refreshWindowList();
    loadPresets();
});

document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("url-input").addEventListener("keydown", function (e) {
        if (e.key === "Enter") addUrl();
    });
});

// ── Theme ──

async function applyOptions() {
    try {
        var tray = await pywebview.api.get_config("minimize_to_tray");
        var cb = document.getElementById("tray-check");
        if (cb) cb.checked = tray !== false; // default true
    } catch (err) {}
}

async function toggleTraySetting() {
    var cb = document.getElementById("tray-check");
    try { await pywebview.api.set_config("minimize_to_tray", cb.checked); } catch (err) {}
}

async function applyTheme() {
    try {
        var theme = await pywebview.api.get_config("theme");
        if (theme === "light") {
            document.body.classList.remove("dark");
            document.body.classList.add("light");
            document.getElementById("theme-btn").textContent = "Dark";
        } else {
            document.body.classList.remove("light");
            document.body.classList.add("dark");
            document.getElementById("theme-btn").textContent = "Light";
        }
    } catch (err) {}
}

async function toggleTheme() {
    var isLight = document.body.classList.contains("light");
    if (isLight) {
        document.body.classList.remove("light");
        document.body.classList.add("dark");
        document.getElementById("theme-btn").textContent = "Light";
        await pywebview.api.set_config("theme", "dark");
    } else {
        document.body.classList.remove("dark");
        document.body.classList.add("light");
        document.getElementById("theme-btn").textContent = "Dark";
        await pywebview.api.set_config("theme", "light");
    }
}

// ── Menu bar ──

function toggleMenu(menuId, e) {
    e.stopPropagation();
    var menu = document.getElementById(menuId);
    // Close all other menus first
    var allMenus = document.querySelectorAll(".menu-dropdown");
    allMenus.forEach(function (m) {
        if (m.id !== menuId) m.classList.add("hidden");
    });
    menu.classList.toggle("hidden");
}

document.addEventListener("click", function (e) {
    // Close all dropdowns when clicking outside
    if (!e.target.closest(".menu-item")) {
        document.querySelectorAll(".menu-dropdown").forEach(function (m) {
            m.classList.add("hidden");
        });
    }
});

// ── Collapsible sections ──

function toggleSection(id) {
    var body = document.getElementById("section-" + id);
    var arrow = document.getElementById("arrow-" + id);
    if (!body) return;
    var collapsed = body.classList.toggle("collapsed");
    if (arrow) arrow.textContent = collapsed ? "\u25B6" : "\u25BC";
    try { pywebview.api.set_config("collapsed_" + id, collapsed); } catch (err) {}
}

async function restoreCollapsedSections() {
    var sections = ["presets", "windows", "external"];
    for (var i = 0; i < sections.length; i++) {
        try {
            var val = await pywebview.api.get_config("collapsed_" + sections[i]);
            if (val === true) {
                var body = document.getElementById("section-" + sections[i]);
                var arrow = document.getElementById("arrow-" + sections[i]);
                if (body) body.classList.add("collapsed");
                if (arrow) arrow.textContent = "\u25B6";
            }
        } catch (err) {}
    }
}

// ── Presets edit mode ──

function togglePresetsEdit(e) {
    e.stopPropagation();
    _presetsEditMode = !_presetsEditMode;
    var btn = document.getElementById("edit-presets-btn");
    if (btn) {
        btn.textContent = _presetsEditMode ? "Done" : "Edit";
        btn.classList.toggle("active", _presetsEditMode);
    }
    loadPresets();
}

// ── URL management ──

async function addUrl() {
    var input = document.getElementById("url-input");
    var url = input.value.trim();
    if (!url) return;
    var fullscreen = document.getElementById("fullscreen-check").checked;
    var fpsLimit = parseInt(document.getElementById("fps-select").value, 10);
    try {
        await pywebview.api.add_url(url, fullscreen, fpsLimit);
        input.value = "";
        await refreshWindowList();
    } catch (err) { console.error("Failed to add URL:", err); }
}

async function closePage(windowId) {
    try {
        await pywebview.api.close_page(windowId);
        await refreshWindowList();
    } catch (err) {}
}

async function focusPage(windowId) {
    try { await pywebview.api.focus_page(windowId); } catch (err) {}
}

async function toggleFullscreen(windowId) {
    try {
        await pywebview.api.toggle_fullscreen_page(windowId);
        await refreshWindowList();
    } catch (err) {}
}

// ── Mirror ──

function getCropRect() {
    if (!document.getElementById("crop-enable").checked) return null;
    var l = parseInt(document.getElementById("crop-left").value, 10) || 0;
    var t = parseInt(document.getElementById("crop-top").value, 10) || 0;
    var w = parseInt(document.getElementById("crop-width").value, 10) || 0;
    var h = parseInt(document.getElementById("crop-height").value, 10) || 0;
    if (w <= 0 || h <= 0) return null;
    return [l, t, l + w, t + h];
}

function toggleCropFields() {
    var fields = document.getElementById("crop-fields");
    fields.classList.toggle("hidden", !document.getElementById("crop-enable").checked);
}

async function openMirrorModal(callback) {
    _mirrorCallback = callback;
    document.getElementById("crop-enable").checked = false;
    document.getElementById("crop-fields").classList.add("hidden");
    try {
        var screens = await pywebview.api.get_screens();
        var list = document.getElementById("screen-list");
        clearElement(list);
        screens.forEach(function (screen) {
            var btn = document.createElement("button");
            btn.className = "screen-btn";
            var label = screen.name + " (" + screen.width + "x" + screen.height + ")";
            if (screen.is_primary) label += " [Primary]";
            btn.textContent = label;
            btn.onclick = function () {
                var cb = _mirrorCallback;
                closeMirrorModal();
                if (cb) cb(screen.index, getCropRect());
            };
            list.appendChild(btn);
        });
        document.getElementById("mirror-modal").classList.remove("hidden");
    } catch (err) { console.error("Failed to get screens:", err); }
}

function closeMirrorModal() {
    document.getElementById("mirror-modal").classList.add("hidden");
    _mirrorCallback = null;
}

async function mirrorPage(windowId) {
    openMirrorModal(async function (screenIndex, cropRect) {
        try {
            await pywebview.api.mirror_page(windowId, screenIndex, cropRect);
            await refreshWindowList();
        } catch (err) { console.error("Failed to mirror:", err); }
    });
}

async function stopMirror(windowId) {
    try {
        await pywebview.api.stop_mirror(windowId);
        await refreshWindowList();
    } catch (err) {}
}

// ── External window mirroring ──

async function loadExternalWindows() {
    try {
        var windows = await pywebview.api.get_external_windows();
        var container = document.getElementById("ext-windows-list");
        clearElement(container);
        if (!windows || windows.length === 0) {
            appendEmpty(container, "No external windows found");
            return;
        }
        windows.forEach(function (win) {
            var row = document.createElement("div");
            row.className = "ext-window-row";
            var titleSpan = document.createElement("span");
            titleSpan.className = "ext-window-title";
            titleSpan.textContent = win.title;
            titleSpan.title = win.title;
            var mirrorBtn = document.createElement("button");
            mirrorBtn.className = "mirror-btn";
            mirrorBtn.textContent = "Mirror";
            mirrorBtn.onclick = function () {
                openMirrorModal(async function (screenIndex, cropRect) {
                    try {
                        await pywebview.api.mirror_external(win.hwnd_int, screenIndex, cropRect);
                        await refreshWindowList();
                    } catch (err) { console.error("Failed to mirror external:", err); }
                });
            };
            row.appendChild(titleSpan);
            row.appendChild(mirrorBtn);
            container.appendChild(row);
        });
    } catch (err) { console.error("Failed to load external windows:", err); }
}

// ── Presets ──

async function loadPresets() {
    try {
        var presets = await pywebview.api.get_presets();
        var container = document.getElementById("presets-grid");
        clearElement(container);
        if (!presets || presets.length === 0) {
            appendEmpty(container, "No presets saved");
            return;
        }
        presets.forEach(function (preset, index) {
            var card = document.createElement("div");
            card.className = "preset-card";
            card.dataset.index = index;
            card.onclick = function () { openPreset(index); };

            // Only enable drag in edit mode
            if (_presetsEditMode) {
                card.draggable = true;
                card.ondragstart = function (e) { e.dataTransfer.setData("text/plain", "preset:" + index); };
                card.ondragover = function (e) { e.preventDefault(); card.classList.add("drag-over"); };
                card.ondragleave = function () { card.classList.remove("drag-over"); };
                card.ondrop = function (e) {
                    e.preventDefault();
                    card.classList.remove("drag-over");
                    var data = e.dataTransfer.getData("text/plain");
                    if (data.startsWith("preset:")) {
                        var fromIdx = parseInt(data.split(":")[1], 10);
                        reorderPresets(fromIdx, index);
                    }
                };
            }

            // Only show delete button in edit mode
            if (_presetsEditMode) {
                var deleteBtn = document.createElement("button");
                deleteBtn.className = "close-btn";
                deleteBtn.textContent = "\u00d7";
                deleteBtn.title = "Delete preset";
                deleteBtn.onclick = function (e) { e.stopPropagation(); deletePreset(index); };
                card.appendChild(deleteBtn);
            }

            var nameLabel = document.createElement("span");
            nameLabel.className = "preset-name";
            nameLabel.textContent = preset.name;

            var urlLabel = document.createElement("span");
            urlLabel.className = "preset-url";
            urlLabel.textContent = extractDomain(preset.url);

            var infoLabel = document.createElement("span");
            infoLabel.className = "preset-info";
            var parts = [];
            if (preset.fullscreen) parts.push("FS");
            if (preset.fps_limit > 0) parts.push(preset.fps_limit + "fps");
            infoLabel.textContent = parts.join(" | ");

            var autoBtn = document.createElement("button");
            autoBtn.className = "auto-btn" + (preset.auto_launch ? " active" : "");
            autoBtn.textContent = "Auto";
            autoBtn.title = preset.auto_launch ? "Auto-launch ON" : "Auto-launch OFF";
            autoBtn.onclick = function (e) { e.stopPropagation(); toggleAutoLaunch(index); };

            card.appendChild(nameLabel);
            card.appendChild(urlLabel);
            card.appendChild(infoLabel);
            card.appendChild(autoBtn);
            container.appendChild(card);
        });
    } catch (err) { console.error("Failed to load presets:", err); }
}

async function savePreset() {
    var input = document.getElementById("url-input");
    var url = input.value.trim();
    if (!url) return;
    var name = prompt("Preset name:");
    if (!name) return;
    var fullscreen = document.getElementById("fullscreen-check").checked;
    var fpsLimit = parseInt(document.getElementById("fps-select").value, 10);
    try {
        await pywebview.api.save_preset(name, url, fullscreen, fpsLimit);
        await loadPresets();
    } catch (err) {}
}

async function savePageAsPreset(url, fullscreen) {
    var name = prompt("Save as preset \u2014 name:");
    if (!name) return;
    try {
        await pywebview.api.save_preset(name, url, fullscreen, 0);
        await loadPresets();
    } catch (err) {}
}

async function openPreset(index) {
    try { await pywebview.api.open_preset(index); await refreshWindowList(); } catch (err) {}
}
async function deletePreset(index) {
    try { await pywebview.api.delete_preset(index); await loadPresets(); } catch (err) {}
}
async function toggleAutoLaunch(index) {
    try { await pywebview.api.toggle_preset_auto_launch(index); await loadPresets(); } catch (err) {}
}
async function reorderPresets(fromIdx, toIdx) {
    try { await pywebview.api.reorder_presets(fromIdx, toIdx); await loadPresets(); } catch (err) {}
}

// ── Open windows list ──

async function refreshWindowList() {
    try {
        var pages = await pywebview.api.get_open_pages();
        var container = document.getElementById("windows-grid");
        clearElement(container);
        if (!pages || pages.length === 0) {
            appendEmpty(container, "No windows open");
            return;
        }
        pages.forEach(function (page) {
            var card = document.createElement("div");
            card.className = "window-card";
            card.draggable = !page.external;
            card.dataset.id = page.id;
            card.onclick = function () { focusPage(page.id); };

            // Right-click to save as preset
            if (!page.external) {
                card.oncontextmenu = function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    savePageAsPreset(page.url, page.fullscreen);
                };
            }

            // Drag events for reordering
            if (!page.external) {
                card.ondragstart = function (e) { e.dataTransfer.setData("text/plain", "win:" + page.id); };
                card.ondragover = function (e) { e.preventDefault(); card.classList.add("drag-over"); };
                card.ondragleave = function () { card.classList.remove("drag-over"); };
                card.ondrop = function (e) {
                    e.preventDefault();
                    card.classList.remove("drag-over");
                    var data = e.dataTransfer.getData("text/plain");
                    if (data.startsWith("win:")) {
                        var fromId = data.split(":")[1];
                        reorderWindows(fromId, page.id);
                    }
                };
            }

            var closeBtn = document.createElement("button");
            closeBtn.className = "close-btn";
            closeBtn.textContent = "\u00d7";
            closeBtn.title = page.external ? "Stop mirror" : "Close";
            closeBtn.onclick = function (e) { e.stopPropagation(); closePage(page.id); };
            card.appendChild(closeBtn);

            if (!page.external) {
                var domain = extractDomain(page.url);
                var favicon = document.createElement("img");
                favicon.className = "favicon";
                favicon.src = "https://www.google.com/s2/favicons?domain=" + domain + "&sz=64";
                favicon.alt = "";
                favicon.onerror = function () { this.style.display = "none"; };
                card.appendChild(favicon);
            }

            var titleLabel = document.createElement("span");
            titleLabel.className = "domain";
            titleLabel.textContent = page.external ? page.title : extractDomain(page.url);
            card.appendChild(titleLabel);

            var actions = document.createElement("div");
            actions.className = "card-actions";

            if (!page.external) {
                var fsBtn = document.createElement("button");
                fsBtn.className = "fs-btn";
                fsBtn.textContent = page.fullscreen ? "Window" : "Fullscr";
                fsBtn.title = page.fullscreen ? "Switch to windowed" : "Switch to fullscreen";
                fsBtn.onclick = function (e) { e.stopPropagation(); toggleFullscreen(page.id); };
                actions.appendChild(fsBtn);
            }

            if (page.mirrored) {
                var stopBtn = document.createElement("button");
                stopBtn.className = "mirror-btn mirrored";
                stopBtn.textContent = "Stop Mirror";
                stopBtn.onclick = function (e) { e.stopPropagation(); stopMirror(page.id); };
                actions.appendChild(stopBtn);
            } else if (!page.external) {
                var mirrorBtn = document.createElement("button");
                mirrorBtn.className = "mirror-btn";
                mirrorBtn.textContent = "Mirror";
                mirrorBtn.onclick = function (e) { e.stopPropagation(); mirrorPage(page.id); };
                actions.appendChild(mirrorBtn);
            }

            card.appendChild(actions);
            container.appendChild(card);
        });
    } catch (err) { console.error("Failed to refresh:", err); }
}

async function reorderWindows(fromId, toId) {
    try { await pywebview.api.reorder_windows(fromId, toId); await refreshWindowList(); } catch (err) {}
}

// ── Helpers ──

function clearElement(el) { while (el.firstChild) el.removeChild(el.firstChild); }

function appendEmpty(container, text) {
    var msg = document.createElement("p");
    msg.className = "empty-msg";
    msg.textContent = text;
    container.appendChild(msg);
}

function extractDomain(url) {
    try { var a = document.createElement("a"); a.href = url; return a.hostname; }
    catch (e) { return url; }
}

function updateResourceStats(cpu, ram, gpu) {
    var cpuEl = document.getElementById("stat-cpu");
    var ramEl = document.getElementById("stat-ram");
    var gpuEl = document.getElementById("stat-gpu");
    if (cpuEl) cpuEl.textContent = "CPU: " + cpu + "%";
    if (ramEl) ramEl.textContent = "RAM: " + ram + " MB";
    if (gpuEl) gpuEl.textContent = gpu !== null ? "GPU: " + gpu + "%" : "GPU: N/A";
}
