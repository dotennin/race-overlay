const HUD_REFERENCE_WIDTH = 1280;
const HUD_REFERENCE_HEIGHT = 720;
const MIN_WIDGET_SIZE = 24;
const GRID_SNAP_SIZE = 8;
const SNAP_THRESHOLD = 6;
const PREVIEW_DEBOUNCE_MS = 120;
const PREVIEW_DRAG_THROTTLE_MS = 90;
const SUPPORTED_ANCHORS = ["top-left", "top-right", "bottom-left", "bottom-right"];
const STYLE_THEME_FALLBACKS = {
  font_family: "font_family",
  font_weight: "font_weight",
  font_size_px: "font_size_px",
  show_unit: "show_units",
  value_font_family: "value_font_family",
  value_font_weight: "value_font_weight",
  value_font_size_px: "value_font_size_px",
  unit_font_family: "unit_font_family",
  unit_font_weight: "unit_font_weight",
  unit_font_size_px: "unit_font_size_px",
  title_font_family: "title_font_family",
  title_font_weight: "title_font_weight",
  title_font_size_px: "title_font_size_px",
};

const elements = {
  statusMessage: document.getElementById("status-message"),
  presetSelect: document.getElementById("preset-select"),
  savePresetButton: document.getElementById("save-preset-button"),
  projectConfigPanel: document.getElementById("project-config-panel"),
  projectActivityFile: document.getElementById("project-activity-file"),
  projectVideoGlobs: document.getElementById("project-video-globs"),
  projectOutputDir: document.getElementById("project-output-dir"),
  videoPreviewModal: document.getElementById("video-preview-modal"),
  videoPreviewGrid: document.getElementById("video-preview-grid"),
  videoPreviewSummary: document.getElementById("video-preview-summary"),
  videoPreviewCloseButton: document.getElementById("video-preview-close-button"),
  browseToggle: document.getElementById("browse-toggle"),
  browsePanel: document.getElementById("browse-panel"),
  overlayLibraryList: document.getElementById("overlay-library-list"),
  layersToggle: document.getElementById("layers-toggle"),
  layersPanel: document.getElementById("layers-panel"),
  themeControls: document.getElementById("theme-controls"),
  themeDefaultsToggle: document.getElementById("theme-defaults-toggle"),
  themeDefaultsPanel: document.getElementById("theme-defaults-panel"),
  widgetList: document.getElementById("widget-list"),
  inspectorContent: document.getElementById("inspector-content"),
  saveButton: document.getElementById("save-button"),
  renderButton: document.getElementById("render-button"),
  renderPanel: document.getElementById("render-panel"),
  renderMinimizeButton: document.getElementById("render-minimize-button"),
  renderDrawerTab: document.getElementById("render-drawer-tab"),
  renderStatus: document.getElementById("render-status"),
  renderProgress: document.getElementById("render-progress"),
  renderPercent: document.getElementById("render-progress-percent"),
  renderStage: document.getElementById("render-stage"),
  renderPreviewToggle: document.getElementById("render-preview-toggle"),
  renderPreviewModal: document.getElementById("render-preview-modal"),
  renderPreviewCloseButton: document.getElementById("render-preview-close-button"),
  renderPreviewStatus: document.getElementById("render-preview-status"),
  renderPreviewImage: document.getElementById("render-preview-image"),
  renderCancelButton: document.getElementById("render-cancel-button"),
  renderConsole: document.getElementById("render-console"),
  helpButton: document.getElementById("help-button"),
  helpCloseButton: document.getElementById("help-close-button"),
  helpModal: document.getElementById("help-modal"),
  preview: document.getElementById("preview"),
  canvasStage: document.getElementById("canvas-stage"),
  widgetOverlays: document.getElementById("widget-overlays"),
  snapGuides: document.getElementById("snap-guides"),
};

let savedState = null;
let draftState = null;
let selectedWidgetId = null;
let previewRequest = 0;
let previewObjectUrl = "";
let previewRefreshTimer = null;
let dragPreviewTimer = null;
let lastPreviewRefreshAt = 0;
let dragPreviewDirty = false;
let activeInteraction = null;
let activeSnapGuides = [];
let renderState = { status: "idle", stage: "", logs: [], error: null, cancel_requested: false, clip_name: null, frame_index: null, frame_total: null, percent: null };
let renderPollTimer = null;
let renderPanelMinimized = false;
let renderPreviewOpen = false;
let videoPreviewOpen = false;
const videoRotationRequests = new Map();
const pendingVideoRotations = new Set();
const pendingVideoRemovals = new Set();
let renderPreviewVersion = 0;
let renderPreviewObjectUrl = "";
let renderPreviewLastFetchAt = 0;
let renderPreviewRequestInFlight = false;
let renderPreviewRequestGeneration = 0;
const accordionStates = {
  browse: true,
  layers: true,
  themeDefaults: false,
};

function cloneWidget(widget) {
  return {
    id: widget.id,
    type: widget.type,
    bindings: Object.assign({}, widget.bindings),
    anchor: widget.anchor,
    x: widget.x,
    y: widget.y,
    width: widget.width,
    height: widget.height,
    z_index: widget.z_index,
    visible: widget.visible,
    style: Object.assign({}, widget.style),
  };
}

function cloneHud(hud) {
  const theme = Object.assign({}, hud.theme);
  const widgets = hud.widgets.map((widget) => cloneWidget(widget));
  return {
    preset: hud.preset,
    theme,
    widgets,
  };
}

function setStatusMessage(message, tone = "error") {
  if (!elements.statusMessage) {
    return;
  }
  elements.statusMessage.textContent = message;
  elements.statusMessage.hidden = !message;
  elements.statusMessage.dataset.tone = tone;
}

function readErrorMessage(error, fallback) {
  return error instanceof Error ? error.message : fallback;
}

function updateRenderButtonState() {
  if (!elements.renderButton) {
    return;
  }
  elements.renderButton.disabled = !draftState || renderState.status === "running";
  elements.renderButton.textContent = renderState.status === "running" ? "Rendering..." : "Render";
}

function clearRenderPreviewUrl() {
  if (renderPreviewObjectUrl && typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function") {
    URL.revokeObjectURL(renderPreviewObjectUrl);
  }
  renderPreviewObjectUrl = "";
  if (elements.renderPreviewImage) {
    elements.renderPreviewImage.removeAttribute("src");
    elements.renderPreviewImage.hidden = true;
  }
}

function clearRenderPreviewPoll() {
  renderPreviewRequestGeneration += 1;
  renderPreviewLastFetchAt = 0;
  renderPreviewRequestInFlight = false;
}

function openRenderPreview() {
  if (!elements.renderPreviewModal) {
    return;
  }
  renderPreviewOpen = true;
  elements.renderPreviewModal.hidden = false;
  if (typeof elements.renderPreviewModal.showModal === "function" && !elements.renderPreviewModal.open) {
    elements.renderPreviewModal.showModal();
  } else {
    elements.renderPreviewModal.open = true;
  }
}

function closeRenderPreview() {
  renderPreviewOpen = false;
  clearRenderPreviewPoll();
  if (!elements.renderPreviewModal) {
    return;
  }
  if (typeof elements.renderPreviewModal.close === "function" && elements.renderPreviewModal.open) {
    elements.renderPreviewModal.close();
  }
  elements.renderPreviewModal.hidden = true;
  elements.renderPreviewModal.open = false;
}

function renderRenderPreviewPane({ loading = false } = {}) {
  if (!elements.renderPreviewToggle || !elements.renderPreviewModal || !elements.renderPreviewStatus || !elements.renderPreviewImage) {
    return;
  }
  elements.renderPreviewToggle.textContent = renderPreviewOpen ? "Hide preview" : "Show preview";
  if (typeof elements.renderPreviewToggle.setAttribute === "function") {
    elements.renderPreviewToggle.setAttribute("aria-expanded", renderPreviewOpen ? "true" : "false");
  } else {
    elements.renderPreviewToggle["aria-expanded"] = renderPreviewOpen ? "true" : "false";
  }
  if (!renderPreviewOpen) {
    elements.renderPreviewModal.hidden = true;
    elements.renderPreviewModal.open = false;
    return;
  }
  elements.renderPreviewModal.hidden = false;

  const hasImage = Boolean(renderPreviewObjectUrl);
  let status = "Preview will appear when rendering starts.";
  let state = "idle";
  if (loading) {
    status = hasImage ? "Refreshing preview…" : "Loading preview…";
    state = "loading";
  } else if (renderPanelMinimized) {
    status = hasImage ? "Preview paused while the render panel is minimized." : "Restore the render panel to load the preview.";
    state = "paused";
  } else if (renderState.status === "running") {
    if (hasImage) {
      status = "Live preview updates automatically while rendering.";
      state = "ready";
    } else if (renderState.preview?.available) {
      status = "Loading latest preview frame…";
      state = "loading";
    } else {
      status = "Waiting for first frame…";
      state = "waiting";
    }
  } else if (hasImage) {
    status = "Last preview frame is ready for inspection.";
    state = "ready";
  }

  elements.renderPreviewModal.dataset.state = state;
  elements.renderPreviewStatus.textContent = status;
  elements.renderPreviewImage.hidden = !hasImage;
}

async function fetchJson(url, fallbackMessage) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error ?? fallbackMessage);
  }
  return payload;
}

function renderRenderPanel() {
  if (!elements.renderPanel || !elements.renderStatus || !elements.renderStage || !elements.renderConsole) {
    return;
  }
  const logs = Array.isArray(renderState.logs) ? renderState.logs : [];
  const status = renderState.status || "idle";
  const stage = renderState.error || renderState.stage || "Ready to render the current draft.";
  const percent = renderState.percent ?? 0;
  const clipName = renderState.clip_name ? ` — ${renderState.clip_name}` : "";
  const frameInfo = renderState.frame_index && renderState.frame_total ? ` (${renderState.frame_index}/${renderState.frame_total})` : "";
  const progressDisplay = percent > 0 && status === "running" ? `${percent}%${clipName}${frameInfo}` : "";
  
  // Determine if render console should be shown
  const shouldShow = status === "running" || (status !== "idle" && logs.length > 0) || renderState.error;
  const panelVisible = !renderPanelMinimized && shouldShow;
  
  // Update panel visibility
  if (panelVisible && elements.renderPanel.hidden) {
    elements.renderPanel.hidden = false;
  } else if (!panelVisible && !elements.renderPanel.hidden) {
    elements.renderPanel.hidden = true;
  }
  
  // Update drawer tab visibility (show when console has content but is minimized)
  if (elements.renderDrawerTab) {
    const showDrawerTab = shouldShow && renderPanelMinimized;
    if (showDrawerTab && elements.renderDrawerTab.hidden) {
      elements.renderDrawerTab.hidden = false;
    } else if (!showDrawerTab && !elements.renderDrawerTab.hidden) {
      elements.renderDrawerTab.hidden = true;
    }
  }
  
  elements.renderStatus.textContent = status;
  elements.renderStage.textContent = stage;
  elements.renderConsole.textContent = logs.length ? logs.join("\n") : "No render output yet.";
  
  if (elements.renderProgress) {
    elements.renderProgress.value = percent;
    elements.renderProgress.hidden = status !== "running";
  }
  if (elements.renderPercent) {
    elements.renderPercent.textContent = progressDisplay;
    elements.renderPercent.hidden = status !== "running";
  }
  if (elements.renderCancelButton) {
    elements.renderCancelButton.hidden = status !== "running";
  }
  updateRenderButtonState();
  renderRenderPreviewPane();
}

function scheduleRenderPoll(delay = 300) {
  if (renderPollTimer) {
    window.clearTimeout(renderPollTimer);
  }
  renderPollTimer = window.setTimeout(() => {
    renderPollTimer = null;
    void pollRenderStatus();
  }, delay);
}

async function postRenderPreviewEnabled(enabled) {
  const response = await fetch("/api/render/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed to update render preview");
  }
  return payload;
}

async function refreshRenderPreview(version) {
  if (!elements.renderPreviewImage || renderPreviewRequestInFlight) {
    return;
  }
  renderPreviewRequestInFlight = true;
  const requestGeneration = renderPreviewRequestGeneration;
  renderRenderPreviewPane({ loading: true });
  try {
    const response = await fetch(`/api/render/preview.png?v=${version}`);
    if (response.status === 204) {
      return;
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error ?? "Failed to load render preview");
    }
    const latestPreviewVersion = Number(renderState.preview?.version ?? 0) || 0;
    if (
      requestGeneration !== renderPreviewRequestGeneration
      || !renderPreviewOpen
      || renderPanelMinimized
      || version !== latestPreviewVersion
    ) {
      return;
    }
    const blob = await response.blob();
    const currentPreviewVersion = Number(renderState.preview?.version ?? 0) || 0;
    if (
      requestGeneration !== renderPreviewRequestGeneration
      || !renderPreviewOpen
      || renderPanelMinimized
      || version !== currentPreviewVersion
    ) {
      return;
    }
    clearRenderPreviewUrl();
    renderPreviewObjectUrl = typeof URL !== "undefined" && typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : "";
    renderPreviewVersion = version;
    renderPreviewLastFetchAt = Date.now();
    if (renderPreviewObjectUrl) {
      elements.renderPreviewImage.src = renderPreviewObjectUrl;
    }
  } finally {
    renderPreviewRequestInFlight = false;
    renderRenderPreviewPane();
  }
}

async function syncRenderPreviewState(previousStatus = renderState.status) {
  const previewState = renderState.preview ?? {};
  const previewVersion = Number(previewState.version ?? 0) || 0;
  const previewAvailable = Boolean(previewState.available);
  const shouldRun = renderPreviewOpen && !renderPanelMinimized && renderState.status === "running";

  if (shouldRun && previewState.enabled !== true) {
    try {
      renderState = await postRenderPreviewEnabled(true);
    } catch (error) {
      setStatusMessage(readErrorMessage(error, "Failed to enable render preview"));
    }
  } else if (!shouldRun && previewState.enabled === true) {
    try {
      renderState = await postRenderPreviewEnabled(false);
      clearRenderPreviewPoll();
    } catch (error) {
      setStatusMessage(readErrorMessage(error, "Failed to disable render preview"));
    }
  }

  const renderJustFinished = previousStatus === "running" && renderState.status !== "running";
  const shouldFetchPreview = renderPreviewOpen
    && !renderPanelMinimized
    && previewAvailable
    && previewVersion > renderPreviewVersion
    && (renderJustFinished || Date.now() - renderPreviewLastFetchAt >= 1000);

  if (shouldFetchPreview) {
    try {
      await refreshRenderPreview(previewVersion);
    } catch (error) {
      setStatusMessage(readErrorMessage(error, "Failed to load render preview"));
    }
  }

  renderRenderPreviewPane();
}

async function pollRenderStatus() {
  const previousStatus = renderState.status;
  try {
    renderState = await fetchJson("/api/render", "Failed to load render status");
    renderRenderPanel();
    await syncRenderPreviewState(previousStatus);
    if (renderState.status === "running") {
      scheduleRenderPoll();
    }
  } catch (error) {
    setStatusMessage(readErrorMessage(error, "Failed to load render status"));
  }
}

async function startRenderJob() {
  if (!draftState) {
    return;
  }
  renderPreviewVersion = 0;
  clearRenderPreviewPoll();
  const response = await fetch("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cloneHud(draftState)),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed to start render");
  }
  renderState = payload;
  renderRenderPanel();
  await syncRenderPreviewState("idle");
  scheduleRenderPoll(150);
}

async function cancelRenderJob() {
  if (!window.confirm("Cancel current render? Partial output will be kept.")) {
    return;
  }
  try {
    const response = await fetch("/api/render/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "Failed to cancel render");
    }
    renderState = payload;
    renderRenderPanel();
    await syncRenderPreviewState("running");
    scheduleRenderPoll(150);
  } catch (error) {
    setStatusMessage(readErrorMessage(error, "Failed to cancel render"));
  }
}

function getWidgetsInLayerOrder() {
  if (!draftState) {
    return [];
  }
  return [...draftState.widgets].sort((left, right) => left.z_index - right.z_index || left.id.localeCompare(right.id));
}

function getWidget(widgetId) {
  return draftState?.widgets.find((widget) => widget.id === widgetId) ?? null;
}

function getWidgetSchema(widgetId) {
  if (!savedState || !savedState.schema) {
    return null;
  }
  const widgetSchema = savedState.schema.widgets?.[widgetId];
  if (widgetSchema) {
    return widgetSchema;
  }
  const widget = getWidget(widgetId);
  if (!widget) {
    return null;
  }
  return savedState.schema.widget_types?.[widget.type] ?? null;
}

function ensureSelection() {
  if (!draftState || draftState.widgets.length === 0) {
    selectedWidgetId = null;
    return;
  }
  if (selectedWidgetId && getWidget(selectedWidgetId)) {
    return;
  }
  const orderedWidgets = getWidgetsInLayerOrder();
  selectedWidgetId = orderedWidgets[orderedWidgets.length - 1]?.id ?? draftState.widgets[0].id;
}

function syncAccordionPanels() {
  [
    ["browse", elements.browseToggle, elements.browsePanel],
    ["layers", elements.layersToggle, elements.layersPanel],
    ["themeDefaults", elements.themeDefaultsToggle, elements.themeDefaultsPanel],
  ].forEach(([key, toggle, panel]) => {
    const isOpen = Boolean(accordionStates[key]);
    if (toggle) {
      if (typeof toggle.setAttribute === "function") {
        toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      } else {
        toggle["aria-expanded"] = isOpen ? "true" : "false";
      }
    }
    if (panel) {
      panel.dataset.open = isOpen ? "true" : "false";
      if (typeof panel.setAttribute === "function") {
        panel.setAttribute("aria-hidden", isOpen ? "false" : "true");
      } else {
        panel["aria-hidden"] = isOpen ? "false" : "true";
      }
    }
  });
}

function toggleAccordion(key, force = null) {
  accordionStates[key] = typeof force === "boolean" ? force : !accordionStates[key];
  syncAccordionPanels();
}

function toggleThemeDefaults(force = null) {
  toggleAccordion("themeDefaults", force);
}

function syncThemeDefaultsAccordion() {
  syncAccordionPanels();
}

function clearPreviewUrl() {
  if (previewObjectUrl && typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function") {
    URL.revokeObjectURL(previewObjectUrl);
  }
  previewObjectUrl = "";
}

function getPreviewDimensions() {
  return {
    width: savedState?.preview?.width ?? HUD_REFERENCE_WIDTH,
    height: savedState?.preview?.height ?? HUD_REFERENCE_HEIGHT,
  };
}

function getRenderedPreviewMetrics() {
  const frame = getPreviewDimensions();
  const renderedWidth = elements.preview?.clientWidth || frame.width;
  const renderedHeight = elements.preview?.clientHeight || frame.height;
  return {
    frameWidth: frame.width,
    frameHeight: frame.height,
    renderedWidth,
    renderedHeight,
    scaleX: renderedWidth / frame.width,
    scaleY: renderedHeight / frame.height,
  };
}

function widgetToRect(widget) {
  const frame = getPreviewDimensions();
  return {
    left: widget.x + (widget.anchor.includes("right") ? frame.width - HUD_REFERENCE_WIDTH : 0),
    top: widget.y + (widget.anchor.includes("bottom") ? frame.height - HUD_REFERENCE_HEIGHT : 0),
    width: widget.width,
    height: widget.height,
  };
}

function rectToWidgetPatch(widget, rect) {
  const frame = getPreviewDimensions();
  return {
    x: Math.round(rect.left - (widget.anchor.includes("right") ? frame.width - HUD_REFERENCE_WIDTH : 0)),
    y: Math.round(rect.top - (widget.anchor.includes("bottom") ? frame.height - HUD_REFERENCE_HEIGHT : 0)),
    width: Math.max(MIN_WIDGET_SIZE, Math.round(rect.width)),
    height: Math.max(MIN_WIDGET_SIZE, Math.round(rect.height)),
  };
}

function clampRect(rect, frame) {
  const width = Math.max(MIN_WIDGET_SIZE, Math.min(rect.width, frame.width));
  const height = Math.max(MIN_WIDGET_SIZE, Math.min(rect.height, frame.height));
  const left = Math.max(0, Math.min(rect.left, frame.width - width));
  const top = Math.max(0, Math.min(rect.top, frame.height - height));
  return { left, top, width, height };
}

function collectSnapGuides(widgetId) {
  const frame = getPreviewDimensions();
  const guides = {
    x: new Set([0, frame.width / 2, frame.width]),
    y: new Set([0, frame.height / 2, frame.height]),
  };
  getWidgetsInLayerOrder().forEach((widget) => {
    if (widget.id === widgetId || !widget.visible) {
      return;
    }
    const rect = widgetToRect(widget);
    guides.x.add(rect.left);
    guides.x.add(rect.left + rect.width / 2);
    guides.x.add(rect.left + rect.width);
    guides.y.add(rect.top);
    guides.y.add(rect.top + rect.height / 2);
    guides.y.add(rect.top + rect.height);
  });
  return {
    x: [...guides.x],
    y: [...guides.y],
  };
}

function snapPosition(value, span, candidates) {
  const guideCandidates = candidates.flatMap((candidate) => [
    { value: candidate, guide: candidate },
    { value: candidate - span / 2, guide: candidate },
    { value: candidate - span, guide: candidate },
  ]);
  let bestGuide = null;
  guideCandidates.forEach((candidate) => {
    const delta = Math.abs(candidate.value - value);
    if (delta > SNAP_THRESHOLD) {
      return;
    }
    if (!bestGuide || delta < bestGuide.delta) {
      bestGuide = { ...candidate, delta, kind: "guide" };
    }
  });
  if (bestGuide) {
    return bestGuide;
  }
  const gridValue = Math.round(value / GRID_SNAP_SIZE) * GRID_SNAP_SIZE;
  const gridDelta = Math.abs(gridValue - value);
  if (gridDelta <= SNAP_THRESHOLD) {
    return { value: gridValue, delta: gridDelta, kind: "grid" };
  }
  return { value, delta: 0, kind: "none" };
}

function snapRectToGuides(rect, widgetId, handle = null) {
  const guides = collectSnapGuides(widgetId);
  const nextRect = { ...rect };
  const guideFeedback = [];
  const horizontal = handle ? (handle.includes("w") ? "left" : handle.includes("e") ? "right" : null) : "left";
  const vertical = handle ? (handle.includes("n") ? "top" : handle.includes("s") ? "bottom" : null) : "top";

  if (horizontal === "left") {
    const snapped = snapPosition(nextRect.left, nextRect.width, guides.x);
    nextRect.left = snapped.value;
    if (snapped.kind === "guide") {
      guideFeedback.push({ axis: "x", position: snapped.guide });
    }
  } else if (horizontal === "right") {
    const snapped = snapPosition(nextRect.left + nextRect.width, nextRect.width, guides.x);
    nextRect.width = Math.max(MIN_WIDGET_SIZE, snapped.value - nextRect.left);
    if (snapped.kind === "guide") {
      guideFeedback.push({ axis: "x", position: snapped.guide });
    }
  }

  if (vertical === "top") {
    const snapped = snapPosition(nextRect.top, nextRect.height, guides.y);
    nextRect.top = snapped.value;
    if (snapped.kind === "guide") {
      guideFeedback.push({ axis: "y", position: snapped.guide });
    }
  } else if (vertical === "bottom") {
    const snapped = snapPosition(nextRect.top + nextRect.height, nextRect.height, guides.y);
    nextRect.height = Math.max(MIN_WIDGET_SIZE, snapped.value - nextRect.top);
    if (snapped.kind === "guide") {
      guideFeedback.push({ axis: "y", position: snapped.guide });
    }
  }

  return { rect: nextRect, guides: guideFeedback };
}

function isDraftDirty() {
  if (!savedState || !draftState) {
    return false;
  }
  return JSON.stringify(savedState.hud) !== JSON.stringify(draftState);
}

function updateSaveButtonState() {
  if (!elements.saveButton) {
    updatePresetControlsState();
    return;
  }
  elements.saveButton.disabled = !savedState || !draftState;
  updatePresetControlsState();
}

function updatePresetControlsState() {
  if (elements.savePresetButton) {
    elements.savePresetButton.disabled = !savedState || !draftState;
  }
  if (!elements.presetSelect) {
    return;
  }
  const presetNames = Array.isArray(savedState?.presets?.names) ? savedState.presets.names : [];
  elements.presetSelect.disabled = !savedState || !draftState || presetNames.length === 0;
}

function schedulePreviewRefresh({ immediate = false, drag = false } = {}) {
  if (!draftState) {
    return;
  }
  const now = Date.now();
  if (immediate) {
    if (dragPreviewTimer) {
      clearTimeout(dragPreviewTimer);
      dragPreviewTimer = null;
    }
    lastPreviewRefreshAt = now;
    dragPreviewDirty = false;
    void refreshPreview().catch((error) => {
      setStatusMessage(readErrorMessage(error, "Failed to render preview"));
    });
    return;
  }

  if (!drag) {
    if (previewRefreshTimer) {
      clearTimeout(previewRefreshTimer);
    }
    previewRefreshTimer = setTimeout(() => {
      previewRefreshTimer = null;
      lastPreviewRefreshAt = Date.now();
      dragPreviewDirty = false;
      void refreshPreview().catch((error) => {
        setStatusMessage(readErrorMessage(error, "Failed to render preview"));
      });
    }, PREVIEW_DEBOUNCE_MS);
    return;
  }

  dragPreviewDirty = true;
  if (dragPreviewTimer) {
    clearTimeout(dragPreviewTimer);
    dragPreviewTimer = null;
  }
  if (now - lastPreviewRefreshAt >= PREVIEW_DRAG_THROTTLE_MS) {
    lastPreviewRefreshAt = now;
    dragPreviewDirty = false;
    void refreshPreview().catch((error) => {
      setStatusMessage(readErrorMessage(error, "Failed to render preview"));
    });
    return;
  }

  dragPreviewTimer = setTimeout(() => {
    dragPreviewTimer = null;
    lastPreviewRefreshAt = Date.now();
    dragPreviewDirty = false;
    void refreshPreview().catch((error) => {
      setStatusMessage(readErrorMessage(error, "Failed to render preview"));
    });
  }, Math.max(PREVIEW_DRAG_THROTTLE_MS - (now - lastPreviewRefreshAt), 0));
}

async function refreshPreview() {
  if (!draftState) {
    return;
  }
  const requestId = ++previewRequest;
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draftState),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error ?? "Failed to render preview");
  }
  if (requestId !== previewRequest) {
    return;
  }
  const blob = await response.blob();
  clearPreviewUrl();
  previewObjectUrl = typeof URL !== "undefined" && typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : "";
  if (previewObjectUrl) {
    elements.preview.src = previewObjectUrl;
  }
  if (isDraftDirty()) {
    setStatusMessage("Previewing local draft changes.", "info");
  } else {
    setStatusMessage("");
  }
}

function syncOverlayBounds() {
  if (
    !elements.canvasStage
    || !elements.preview
    || !elements.widgetOverlays
    || typeof elements.canvasStage.getBoundingClientRect !== "function"
    || typeof elements.preview.getBoundingClientRect !== "function"
  ) {
    return;
  }
  const stageRect = elements.canvasStage.getBoundingClientRect();
  const previewRect = elements.preview.getBoundingClientRect();
  if (!previewRect.width || !previewRect.height) {
    return;
  }
  elements.widgetOverlays.style.left = `${previewRect.left - stageRect.left}px`;
  elements.widgetOverlays.style.top = `${previewRect.top - stageRect.top}px`;
  elements.widgetOverlays.style.width = `${previewRect.width}px`;
  elements.widgetOverlays.style.height = `${previewRect.height}px`;
  if (elements.snapGuides) {
    elements.snapGuides.style.left = `${previewRect.left - stageRect.left}px`;
    elements.snapGuides.style.top = `${previewRect.top - stageRect.top}px`;
    elements.snapGuides.style.width = `${previewRect.width}px`;
    elements.snapGuides.style.height = `${previewRect.height}px`;
  }
}

function nextOverlayWidgetId(baseId) {
  if (!draftState) {
    return baseId;
  }
  const existingIds = new Set(draftState.widgets.map((widget) => widget.id));
  if (!existingIds.has(baseId)) {
    return baseId;
  }
  let suffix = 2;
  let candidate = `${baseId}-${suffix}`;
  while (existingIds.has(candidate)) {
    suffix += 1;
    candidate = `${baseId}-${suffix}`;
  }
  return candidate;
}

function addOverlayFromLibrary(entry) {
  if (!draftState || !entry?.defaults) {
    return;
  }
  const widget = cloneWidget(entry.defaults);
  widget.id = nextOverlayWidgetId(widget.id);
  draftState.widgets.push(widget);
  selectedWidgetId = widget.id;
  renderWidgetSelection();
  renderInspector();
  renderCanvasOverlays();
  schedulePreviewRefresh();
  updateSaveButtonState();
  setStatusMessage(`Added ${entry.label}.`, "info");
}

function renderOverlayLibrary() {
  if (!elements.overlayLibraryList) {
    return;
  }
  elements.overlayLibraryList.innerHTML = "";
  const catalog = savedState?.overlay_library ?? [];
  if (catalog.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Overlay presets load here when the editor state is ready.";
    elements.overlayLibraryList.appendChild(empty);
    return;
  }

  catalog.forEach((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "overlay-library-item";
    button.addEventListener("click", () => addOverlayFromLibrary(entry));

    const title = document.createElement("p");
    title.className = "overlay-library-item__title";
    title.textContent = entry.label;
    button.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "overlay-library-item__meta";
    meta.textContent = entry.type.replaceAll("_", " ");
    button.appendChild(meta);

    elements.overlayLibraryList.appendChild(button);
  });
}

function renderWidgetSelection() {
  if (!elements.widgetList) {
    return;
  }
  elements.widgetList.innerHTML = "";
  if (!draftState) {
    return;
  }

  const widgets = getWidgetsInLayerOrder().reverse();
  widgets.forEach((widget) => {
    const item = document.createElement("article");
    item.className = `layer-item${widget.id === selectedWidgetId ? " is-selected" : ""}${widget.visible ? "" : " is-hidden"}`;

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "layer-select";
    selectButton.addEventListener("click", () => {
      selectedWidgetId = widget.id;
      renderWidgetSelection();
      renderInspector();
      renderCanvasOverlays();
    });

    const title = document.createElement("h3");
    title.className = "layer-item__title";
    title.textContent = widget.style.label || widget.id;
    selectButton.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "layer-item__meta";
    meta.textContent = `${widget.type} · z ${widget.z_index}`;
    selectButton.appendChild(meta);
    item.appendChild(selectButton);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "layer-item__remove";
    removeButton.title = "Remove this layer";
    removeButton.textContent = "×";
    removeButton.addEventListener("click", (e) => {
      e.stopPropagation();
      if (confirm(`Remove layer "${widget.style.label || widget.id}"?`)) {
        draftState.widgets = draftState.widgets.filter((w) => w.id !== widget.id);
        if (selectedWidgetId === widget.id) {
          selectedWidgetId = draftState.widgets[0]?.id ?? null;
        }
        renderWidgetSelection();
        renderInspector();
        renderCanvasOverlays();
      }
    });
    item.appendChild(removeButton);

    elements.widgetList.appendChild(item);
  });
}

function appendField(parent, labelText, control, fullWidth = false) {
  const wrapper = document.createElement("label");
  wrapper.className = `field${fullWidth ? " field--full" : ""}`;
  const text = document.createElement("span");
  text.textContent = labelText;
  wrapper.appendChild(text);
  wrapper.appendChild(control);
  parent.appendChild(wrapper);
}

function buildTextInput(value, onChange, type = "text", onInput = null) {
  const input = document.createElement("input");
  input.type = type;
  let currentValue = value ?? "";
  input.value = currentValue;
  input.addEventListener("input", () => {
    currentValue = input.value;
    (onInput ?? onChange)(currentValue);
  });
  input.addEventListener("change", () => onChange(input.value));
  return input;
}

function parseIntegerInput(rawValue) {
  if (rawValue.trim() === "") {
    return null;
  }
  const nextValue = Number(rawValue);
  if (!Number.isFinite(nextValue) || !Number.isInteger(nextValue)) {
    return null;
  }
  return nextValue;
}

function buildNumberInput(value, onChange, options = {}, onInput = null) {
  const input = document.createElement("input");
  input.type = "number";
  let currentValue = value;
  input.value = String(currentValue);
  input.step = String(options.step ?? 1);
  if (options.min !== undefined) {
    input.min = String(options.min);
  }
  if (options.max !== undefined) {
    input.max = String(options.max);
  }
  input.addEventListener("input", () => {
    const nextValue = parseIntegerInput(input.value);
    if (nextValue === null) {
      return;
    }
    currentValue = nextValue;
    (onInput ?? onChange)(nextValue);
  });
  input.addEventListener("change", () => {
    const nextValue = parseIntegerInput(input.value);
    if (nextValue === null) {
      input.value = String(currentValue);
      return;
    }
    currentValue = nextValue;
    onChange(nextValue);
  });
  return input;
}

function buildRangeInput(value, onChange, options = {}, onInput = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "range-input";
  const input = document.createElement("input");
  const valueText = document.createElement("span");
  let currentValue = Number(value);

  input.type = "range";
  input.min = String(options.min ?? 0);
  input.max = String(options.max ?? 100);
  input.step = String(options.step ?? 1);
  input.value = String(currentValue);
  valueText.textContent = `${currentValue}${options.suffix ?? ""}`;

  function emit(nextValue, live) {
    currentValue = nextValue;
    valueText.textContent = `${currentValue}${options.suffix ?? ""}`;
    (live ? (onInput ?? onChange) : onChange)(currentValue);
  }

  input.addEventListener("input", () => emit(Number(input.value), true));
  input.addEventListener("change", () => emit(Number(input.value), false));
  wrapper.append(input, valueText);
  return wrapper;
}

function buildCheckbox(value, onChange) {
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(value);
  input.addEventListener("change", () => onChange(input.checked));
  return input;
}

function buildSelectInput(value, options, onChange, onInput = null) {
  const select = document.createElement("select");
  options.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue;
    option.selected = optionValue === value;
    select.appendChild(option);
  });
  select.addEventListener("input", () => (onInput ?? onChange)(select.value));
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function rgbToHex(rgb) {
  return "#" + ((1 << 24) + (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]).toString(16).slice(1);
}

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)] : [255, 255, 255];
}

function buildColorInput(value, onChange, onInput = null, labelText = "RGBA") {
  const rgba = Array.isArray(value) && value.length === 4 ? [...value] : [255, 255, 255, 255];
  const wrapper = document.createElement("div");
  wrapper.className = "color-alpha-input";

  const input = document.createElement("input");
  input.type = "color";
  input.value = rgbToHex(rgba.slice(0, 3));
  input.setAttribute("aria-label", `${labelText} color`);
  input.addEventListener("input", () => emitColorChange());

  const alpha = document.createElement("input");
  alpha.type = "number";
  alpha.min = "0";
  alpha.max = "255";
  alpha.value = String(rgba[3]);
  alpha.setAttribute("aria-label", `${labelText} alpha`);
  alpha.addEventListener("input", () => emitColorChange());

  function emitColorChange() {
    const [r, g, b] = hexToRgb(input.value);
    const next = [r, g, b, Number(alpha.value)];
    (onInput ?? onChange)(next);
  }

  wrapper.append(input, alpha);
  return wrapper;
}

function renderFieldControl(parent, key, metadata, value, onChange, onInput = null) {
  if (metadata?.hidden) {
    return;
  }
  const fieldLabel = metadata?.label ?? key;
  if (metadata?.kind === "boolean" || typeof value === "boolean") {
    const toggle = document.createElement("label");
    toggle.className = "toggle-field";
    const text = document.createElement("span");
    text.textContent = fieldLabel;
    toggle.appendChild(text);
    toggle.appendChild(buildCheckbox(Boolean(value), onChange));
    parent.appendChild(toggle);
    return;
  }
  if (metadata?.kind === "rgba") {
    appendField(parent, fieldLabel, buildColorInput(value, onChange, onInput, fieldLabel), true);
    return;
  }
  if (metadata?.kind === "enum" || metadata?.kind === "selection") {
    appendField(parent, fieldLabel, buildSelectInput(value, metadata.options ?? [], onChange, onInput), true);
    return;
  }
  if (metadata?.kind === "range") {
    appendField(
      parent,
      fieldLabel,
      buildRangeInput(value, onChange, {
        min: metadata?.min,
        max: metadata?.max,
        step: metadata?.step,
        suffix: metadata?.suffix,
      }, onInput),
      true,
    );
    return;
  }
  if (metadata?.kind === "integer" || typeof value === "number") {
    appendField(parent, fieldLabel, buildNumberInput(value, onChange, { min: metadata?.min }, onInput), false);
    return;
  }
  appendField(parent, fieldLabel, buildTextInput(String(value ?? ""), onChange, "text", onInput), true);
}

function updateThemeField(key, nextValue, { live = false } = {}) {
  if (!draftState) {
    return;
  }
  draftState.theme = Object.assign({}, draftState.theme, { [key]: nextValue });
  if (!live) {
    renderThemeControls();
    renderInspector();
  }
  schedulePreviewRefresh();
  updateSaveButtonState();
}

function renderThemeControls() {
  if (!elements.themeControls) {
    return;
  }
  elements.themeControls.innerHTML = "";
  if (!draftState) {
    return;
  }
  const themeSchema = savedState && savedState.schema ? savedState.schema.theme ?? {} : {};
  const themeCard = document.createElement("section");
  themeCard.className = "inspector-card";
  const themeGrid = document.createElement("div");
  themeGrid.className = "inspector-grid";
  Object.entries(themeSchema).forEach(([key, metadata]) => {
    renderFieldControl(
      themeGrid,
      key,
      metadata,
      draftState.theme[key],
      (nextValue) => updateThemeField(key, nextValue),
      (nextValue) => updateThemeField(key, nextValue, { live: true }),
    );
  });
  themeCard.appendChild(themeGrid);
  elements.themeControls.appendChild(themeCard);
}

function buildProjectSummary(labelText, valueText) {
  const wrapper = document.createElement("div");
  wrapper.className = "project-config-summary";
  const label = document.createElement("span");
  label.className = "field-hint";
  label.textContent = labelText;
  const value = document.createElement("p");
  value.className = "project-config-summary__value";
  value.textContent = valueText;
  wrapper.append(label, value);
  return wrapper;
}

async function saveProjectState(payload) {
  const response = await fetch("/api/project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error ?? "Failed to save project settings");
  }
  await loadState();
  setStatusMessage("Saved project settings.", "info");
}

function closeVideoPreview() {
  videoPreviewOpen = false;
  elements.videoPreviewGrid?.querySelectorAll("video").forEach((video) => video.pause());
  if (!elements.videoPreviewModal) {
    return;
  }
  if (
    typeof elements.videoPreviewModal.close === "function"
    && elements.videoPreviewModal.open
  ) {
    elements.videoPreviewModal.close();
  }
  elements.videoPreviewModal.hidden = true;
  elements.videoPreviewModal.open = false;
}

function openVideoPreview() {
  if (!elements.videoPreviewModal) {
    return;
  }
  videoPreviewOpen = true;
  renderVideoPreviewGrid();
  elements.videoPreviewModal.hidden = false;
  if (
    typeof elements.videoPreviewModal.showModal === "function"
    && !elements.videoPreviewModal.open
  ) {
    elements.videoPreviewModal.showModal();
  } else {
    elements.videoPreviewModal.open = true;
  }
}

function stopOtherVideoPreviews(activeVideo) {
  elements.videoPreviewGrid?.querySelectorAll("video").forEach((video) => {
    if (video !== activeVideo) {
      video.pause();
    }
  });
}

function sizeRotatedVideo(viewport, video, degrees) {
  const sideways = degrees === 90 || degrees === 270;
  const viewportWidth = viewport.clientWidth;
  const viewportHeight = viewport.clientHeight;
  if (!viewportWidth || !viewportHeight) {
    return;
  }
  video.style.width = `${sideways ? viewportHeight : viewportWidth}px`;
  video.style.height = `${sideways ? viewportWidth : viewportHeight}px`;
  video.style.transform = `translate(-50%, -50%) rotate(${degrees}deg)`;
}

function getVideoPreviewRotationSnapshot(item) {
  return {
    user_rotation_degrees: item.user_rotation_degrees,
    effective_rotation_degrees: item.effective_rotation_degrees,
    display_width: item.display_width,
    display_height: item.display_height,
  };
}

function restoreVideoPreviewRotationSnapshot(item, snapshot) {
  item.user_rotation_degrees = snapshot.user_rotation_degrees;
  item.effective_rotation_degrees = snapshot.effective_rotation_degrees;
  item.display_width = snapshot.display_width;
  item.display_height = snapshot.display_height;
}

function applyVideoPreviewRotation(item, rotationDegrees) {
  item.user_rotation_degrees = rotationDegrees;
  item.effective_rotation_degrees = (
    Number(item.source_rotation_degrees || 0) + rotationDegrees
  ) % 360;
  const encodedWidth = Number(item.encoded_width);
  const encodedHeight = Number(item.encoded_height);
  if (encodedWidth && encodedHeight) {
    const sideways = item.effective_rotation_degrees === 90
      || item.effective_rotation_degrees === 270;
    item.display_width = sideways ? encodedHeight : encodedWidth;
    item.display_height = sideways ? encodedWidth : encodedHeight;
  }
}

function updateVideoPreviewCardRotation(card, item) {
  const viewport = card.querySelector(".video-preview-card__viewport");
  const video = card.querySelector("video");
  const rotateButton = card.querySelector(".video-preview-card__rotate");
  const angle = card.querySelector(".video-preview-card__angle");
  const width = Number(item.display_width) || 16;
  const height = Number(item.display_height) || 9;
  if (viewport) {
    viewport.style.aspectRatio = `${width} / ${height}`;
  }
  if (video && viewport) {
    sizeRotatedVideo(viewport, video, Number(item.user_rotation_degrees) || 0);
  }
  if (rotateButton) {
    rotateButton.disabled = pendingVideoRotations.has(item.id);
  }
  if (angle) {
    angle.textContent = `${Number(item.user_rotation_degrees) || 0}°`;
  }
}

async function saveVideoRotation(videoId, rotationDegrees, requestSequence) {
  const project = savedState?.project;
  if (!project?.revision) {
    throw new Error("Project state is unavailable");
  }
  const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/rotation`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rotation_degrees: rotationDegrees,
      revision: project.revision,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (requestSequence !== videoRotationRequests.get(videoId)) {
    return false;
  }
  if (response.status === 409 && payload.project) {
    savedState.project = payload.project;
    renderProjectControls();
    renderVideoPreviewGrid();
    throw new Error(payload.error ?? "Video rotation conflicted with a newer project save");
  }
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed save video rotation");
  }
  const video = project.videos?.find((item) => item.id === videoId);
  if (video) {
    applyVideoPreviewRotation(video, payload.rotation_degrees);
  }
  project.revision = payload.revision;
  return true;
}

async function removeVideoFromProject(videoId) {
  const project = savedState?.project;
  if (!project?.revision) {
    throw new Error("Project state is unavailable");
  }
  const response = await fetch(`/api/videos/${videoId}/remove`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision: project.revision }),
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 409 && payload.project) {
    savedState.project = payload.project;
    renderProjectControls();
    renderVideoPreviewGrid();
    throw new Error(payload.error ?? "Video removal conflicted with newer project save");
  }
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed remove video");
  }
  project.revision = payload.revision;
  await loadState();
  renderVideoPreviewGrid();
}

function renderVideoPreviewGrid() {
  if (!elements.videoPreviewGrid || !elements.videoPreviewSummary) {
    return;
  }
  const videos = Array.isArray(savedState?.project?.videos)
    ? savedState.project.videos
    : [];
  elements.videoPreviewSummary.textContent = `${videos.length} video(s)`;
  elements.videoPreviewGrid.innerHTML = "";
  if (!videos.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No videos match the current video_globs.";
    elements.videoPreviewGrid.appendChild(empty);
    return;
  }
  videos.forEach((item) => {
    const card = document.createElement("article");
    card.className = "video-preview-card";
    const title = document.createElement("h3");
    title.className = "video-preview-card__title";
    title.textContent = item.display_path || item.name;
    title.title = item.display_path || item.name;
    const viewport = document.createElement("div");
    viewport.className = "video-preview-card__viewport";
    const width = Number(item.display_width) || 16;
    const height = Number(item.display_height) || 9;
    viewport.style.aspectRatio = `${width} / ${height}`;
    if (item.error) {
      const error = document.createElement("div");
      error.className = "video-preview-card__error";
      error.textContent = item.error;
      viewport.appendChild(error);
    } else {
      const video = document.createElement("video");
      video.className = "video-preview-card__video";
      video.src = item.media_url;
      video.preload = "metadata";
      video.playsInline = true;
      video.controls = true;
      const applySize = () => sizeRotatedVideo(
        viewport,
        video,
        Number(item.user_rotation_degrees) || 0,
      );
      video.addEventListener("loadedmetadata", applySize);
      video.addEventListener("play", () => stopOtherVideoPreviews(video));
      viewport.appendChild(video);
      if (typeof ResizeObserver === "function") {
        const observer = new ResizeObserver(applySize);
        observer.observe(viewport);
      }
    }
    const actions = document.createElement("div");
    actions.className = "video-preview-card__actions";
    const rotateButton = document.createElement("button");
    rotateButton.type = "button";
    rotateButton.className = "video-preview-card__rotate";
    rotateButton.textContent = "↻ Rotate 90°";
    rotateButton.disabled = pendingVideoRotations.has(item.id);
    const angle = document.createElement("span");
    angle.className = "video-preview-card__angle";
    angle.textContent = `${Number(item.user_rotation_degrees) || 0}°`;
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "video-preview-card__remove";
    removeButton.textContent = "×";
    removeButton.setAttribute("aria-label", "Remove video from project");
    removeButton.title = "Remove video from project";
    removeButton.disabled = pendingVideoRemovals.has(item.id);
    rotateButton.addEventListener("click", async () => {
      const previous = getVideoPreviewRotationSnapshot(item);
      const next = ((Number(item.user_rotation_degrees) || 0) + 90) % 360;
      const sequence = (videoRotationRequests.get(item.id) || 0) + 1;
      videoRotationRequests.set(item.id, sequence);
      pendingVideoRotations.add(item.id);
      applyVideoPreviewRotation(item, next);
      updateVideoPreviewCardRotation(card, item);
      try {
        await saveVideoRotation(item.id, next, sequence);
        if (sequence === videoRotationRequests.get(item.id)) {
          updateVideoPreviewCardRotation(card, item);
        }
      } catch (error) {
        if (sequence === videoRotationRequests.get(item.id)) {
          restoreVideoPreviewRotationSnapshot(item, previous);
          updateVideoPreviewCardRotation(card, item);
          setStatusMessage(readErrorMessage(error, "Failed save video rotation"));
        }
      } finally {
        if (sequence === videoRotationRequests.get(item.id)) {
          pendingVideoRotations.delete(item.id);
          updateVideoPreviewCardRotation(card, item);
        }
      }
    });
    removeButton.addEventListener("click", async () => {
      pendingVideoRemovals.add(item.id);
      renderVideoPreviewGrid();
      try {
        await removeVideoFromProject(item.id);
        setStatusMessage("Removed video from project.", "info");
      } catch (error) {
        setStatusMessage(readErrorMessage(error, "Failed remove video"));
      } finally {
        pendingVideoRemovals.delete(item.id);
        renderVideoPreviewGrid();
      }
    });
    actions.append(rotateButton, angle);
    card.append(removeButton, title, viewport, actions);
    elements.videoPreviewGrid.appendChild(card);
  });
}

function renderPresetControls() {
  if (!elements.presetSelect) {
    return;
  }
  const presetNames = Array.isArray(savedState?.presets?.names) ? savedState.presets.names : [];
  const activePreset = draftState?.preset || savedState?.presets?.active || "";
  elements.presetSelect.innerHTML = "";
  presetNames.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.presetSelect.appendChild(option);
  });
  if (activePreset) {
    elements.presetSelect.value = activePreset;
  }
  updatePresetControlsState();
}

async function savePreset() {
  if (!savedState || !draftState) {
    return;
  }
  const suggestedName = draftState.preset || savedState.presets?.active || "custom-preset";
  const rawName = window.prompt("Preset name", suggestedName);
  if (rawName === null) {
    return;
  }
  const name = rawName.trim();
  if (!name) {
    setStatusMessage("Preset name is required.");
    return;
  }
  const presetNames = new Set(Array.isArray(savedState?.presets?.names) ? savedState.presets.names : []);
  const overwrite = presetNames.has(name);
  if (overwrite && !window.confirm(`Overwrite preset "${name}"?`)) {
    return;
  }
  try {
    const response = await fetch("/api/presets/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        hud: cloneHud(draftState),
        revision: savedState.revision,
        overwrite,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error ?? "Failed to save preset");
    }
    setStatusMessage(`Saved preset "${name}".`, "info");
    await loadState();
  } catch (error) {
    setStatusMessage(readErrorMessage(error, "Failed to save preset"));
  }
}

async function selectPreset(name) {
  if (!savedState || !draftState || !name) {
    renderPresetControls();
    return;
  }
  const currentPreset = savedState?.presets?.active || savedState?.hud?.preset || "";
  if (name === currentPreset && !isDraftDirty()) {
    renderPresetControls();
    return;
  }
  if (isDraftDirty() && !window.confirm(`Switch to preset "${name}" and discard unsaved local changes?`)) {
    renderPresetControls();
    return;
  }
  try {
    const response = await fetch("/api/presets/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error ?? "Failed to load preset");
    }
    setStatusMessage(`Loaded preset "${name}".`, "info");
    await loadState();
  } catch (error) {
    setStatusMessage(readErrorMessage(error, "Failed to load preset"));
    renderPresetControls();
  }
}

async function pickProjectPath(field) {
  const response = await fetch("/api/project/picker", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed to choose project path");
  }
  return payload.value ?? null;
}

function buildProjectPickerButton(labelText, field, onSelection) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = labelText;
  button.addEventListener("click", async () => {
    const value = await pickProjectPath(field);
    if (!value || (Array.isArray(value) && value.length === 0)) {
      return;
    }
    await onSelection(value);
  });
  return button;
}

function renderProjectControls() {
  if (
    !elements.projectConfigPanel
    || !elements.projectActivityFile
    || !elements.projectVideoGlobs
    || !elements.projectOutputDir
  ) {
    return;
  }
  const project = savedState?.project;
  const selectedVideos = Array.isArray(project?.video_globs) ? [...project.video_globs] : [];

  elements.projectActivityFile.innerHTML = "";
  elements.projectVideoGlobs.innerHTML = "";
  elements.projectOutputDir.innerHTML = "";

  if (!project) {
    return;
  }

  const activityCard = document.createElement("section");
  activityCard.className = "project-config-card";
  activityCard.appendChild(buildProjectSummary("Current activity_file", project.activity_file || "Not set"));
  appendField(
    activityCard,
    "Choose activity file",
    buildProjectPickerButton("Choose activity file", "activity_file", async (value) => {
        try {
          await saveProjectState({ activity_file: value });
        } catch (error) {
          setStatusMessage(readErrorMessage(error, "Failed to save project settings"));
        }
      }),
    true,
  );
  elements.projectActivityFile.appendChild(activityCard);

  const videosCard = document.createElement("section");
  videosCard.className = "project-config-card";
  const videosSummaryText = selectedVideos.length 
    ? `${selectedVideos.length} file(s) selected`
    : "Not set";
  videosCard.appendChild(buildProjectSummary("Current video_globs", videosSummaryText));
  videosCard.appendChild(
    buildProjectPickerButton("Choose video files", "video_globs", async (value) => {
        try {
          await saveProjectState({ video_globs: value });
        } catch (error) {
          setStatusMessage(readErrorMessage(error, "Failed to save project settings"));
      }
    }),
  );
  const previewVideosButton = document.createElement("button");
  previewVideosButton.type = "button";
  previewVideosButton.textContent = `Preview all videos (${project.videos?.length || 0})`;
  previewVideosButton.disabled = !project.videos?.length;
  previewVideosButton.addEventListener("click", openVideoPreview);
  videosCard.appendChild(previewVideosButton);
  elements.projectVideoGlobs.appendChild(videosCard);

  const outputCard = document.createElement("section");
  outputCard.className = "project-config-card";
  outputCard.appendChild(buildProjectSummary("Current output_dir", project.output_dir || "Not set"));
  appendField(
    outputCard,
    "Output directory",
    buildProjectPickerButton("Choose output folder", "output_dir", async (value) => {
        try {
          await saveProjectState({ output_dir: value });
        } catch (error) {
          setStatusMessage(readErrorMessage(error, "Failed to save project settings"));
        }
      }),
    true,
  );
  elements.projectOutputDir.appendChild(outputCard);
}

function getStyleFieldValue(widget, key) {
  if (Object.prototype.hasOwnProperty.call(widget.style, key)) {
    return widget.style[key];
  }
  if (widget.type === "progress_bar" && key === "current_font_size_px") {
    const baseFontSize = Number(getStyleFieldValue(widget, "font_size_px"));
    return Number.isFinite(baseFontSize) ? Math.max(baseFontSize - 2, 8) : 8;
  }
  const themeKey = STYLE_THEME_FALLBACKS[key];
  if (themeKey && draftState?.theme) {
    return draftState.theme[themeKey];
  }
  return "";
}

function renderInspector() {
  if (!elements.inspectorContent) {
    return;
  }
  elements.inspectorContent.innerHTML = "";
  if (!draftState) {
    renderPresetControls();
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Load a HUD document to inspect widgets.";
    elements.inspectorContent.appendChild(empty);
    return;
  }

  renderPresetControls();
  renderThemeControls();
  syncThemeDefaultsAccordion();

  const widget = getWidget(selectedWidgetId);
  if (!widget) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Choose a widget layer to edit its geometry and style.";
    elements.inspectorContent.appendChild(empty);
    return;
  }

  const geometryCard = document.createElement("section");
  geometryCard.className = "inspector-card";
  const heading = document.createElement("h3");
  heading.textContent = widget.id;
  geometryCard.appendChild(heading);

  const subheading = document.createElement("p");
  subheading.className = "field-hint";
  subheading.textContent = `${widget.type} · ${widget.bindings.value ?? "binding"}`;
  geometryCard.appendChild(subheading);

  const visibleRow = document.createElement("label");
  visibleRow.className = "toggle-field";
  const visibleLabel = document.createElement("span");
  visibleLabel.textContent = "Visible";
  visibleRow.appendChild(visibleLabel);
  visibleRow.appendChild(buildCheckbox(widget.visible, (value) => updateWidget(widget.id, { visible: value })));
  geometryCard.appendChild(visibleRow);

  const geometryGrid = document.createElement("div");
  geometryGrid.className = "inspector-grid";

  appendField(
    geometryGrid,
    "Anchor",
    buildSelectInput(
      widget.anchor,
      SUPPORTED_ANCHORS,
      (value) => updateWidget(widget.id, { anchor: value }),
      (value) => updateWidget(widget.id, { anchor: value }, { live: true }),
    ),
    true,
  );
  appendField(
    geometryGrid,
    "X",
    buildNumberInput(widget.x, (value) => updateWidget(widget.id, { x: value }), {}, (value) => updateWidget(widget.id, { x: value }, { live: true })),
    false,
  );
  appendField(
    geometryGrid,
    "Y",
    buildNumberInput(widget.y, (value) => updateWidget(widget.id, { y: value }), {}, (value) => updateWidget(widget.id, { y: value }, { live: true })),
    false,
  );
  appendField(
    geometryGrid,
    "Width",
    buildNumberInput(widget.width, (value) => updateWidget(widget.id, { width: value }), {}, (value) => updateWidget(widget.id, { width: value }, { live: true })),
    false,
  );
  appendField(
    geometryGrid,
    "Height",
    buildNumberInput(widget.height, (value) => updateWidget(widget.id, { height: value }), {}, (value) => updateWidget(widget.id, { height: value }, { live: true })),
    false,
  );
  appendField(
    geometryGrid,
    "Z index",
    buildNumberInput(widget.z_index, (value) => updateWidget(widget.id, { z_index: value }), {}, (value) => updateWidget(widget.id, { z_index: value }, { live: true })),
    true,
  );

  const styleCard = document.createElement("section");
  styleCard.className = "inspector-card";
  const styleHeading = document.createElement("h3");
  styleHeading.textContent = "Style";
  styleCard.appendChild(styleHeading);

  const styleGrid = document.createElement("div");
  styleGrid.className = "inspector-grid";
  const widgetSchema = getWidgetSchema(widget.id);
  const styleSchema = widgetSchema?.style ?? {};
  const styleKeys = Array.from(new Set([...Object.keys(styleSchema), ...Object.keys(widget.style)]));
  if (styleKeys.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "This widget does not expose extra style controls.";
    styleCard.appendChild(empty);
  } else {
    styleKeys.forEach((key) => {
      renderFieldControl(
        styleGrid,
        key,
        styleSchema[key],
        getStyleFieldValue(widget, key),
        (nextValue) => {
          updateWidgetStyle(widget.id, key, nextValue);
        },
        (nextValue) => {
          updateWidgetStyle(widget.id, key, nextValue, { live: true });
        },
      );
      });
      styleCard.appendChild(styleGrid);
  }
  geometryCard.appendChild(geometryGrid);
  elements.inspectorContent.appendChild(styleCard);
  elements.inspectorContent.appendChild(geometryCard);
}

function renderSnapGuides(guides = activeSnapGuides) {
  if (!elements.snapGuides) {
    return;
  }
  elements.snapGuides.innerHTML = "";
  guides.forEach((guide) => {
    const line = document.createElement("span");
    line.className = `snap-guide snap-guide--${guide.axis}`;
    if (guide.axis === "x") {
      line.style.left = `${guide.position}px`;
    } else {
      line.style.top = `${guide.position}px`;
    }
    elements.snapGuides.appendChild(line);
  });
}

function renderCanvasOverlays() {
  if (!elements.widgetOverlays) {
    return;
  }
  elements.widgetOverlays.innerHTML = "";
  if (!draftState) {
    return;
  }

  syncOverlayBounds();
  const metrics = getRenderedPreviewMetrics();
  getWidgetsInLayerOrder().forEach((widget) => {
    const rect = widgetToRect(widget);
    const overlay = document.createElement("div");
    overlay.className = `widget-overlay${widget.id === selectedWidgetId ? " is-selected" : ""}${widget.visible ? "" : " is-hidden"}`;
    overlay.style.left = `${rect.left * metrics.scaleX}px`;
    overlay.style.top = `${rect.top * metrics.scaleY}px`;
    overlay.style.width = `${rect.width * metrics.scaleX}px`;
    overlay.style.height = `${rect.height * metrics.scaleY}px`;
    overlay.style.zIndex = String(widget.z_index);
    overlay.dataset.widgetId = widget.id;
    overlay.addEventListener("pointerdown", (event) => beginInteraction(event, widget.id, null));

    ["nw", "ne", "sw", "se"].forEach((handleName) => {
      const handle = document.createElement("div");
      handle.className = "widget-overlay__handle";
      handle.dataset.handle = handleName;
      handle.addEventListener("pointerdown", (event) => beginInteraction(event, widget.id, handleName));
      overlay.appendChild(handle);
    });

    elements.widgetOverlays.appendChild(overlay);
  });
  renderSnapGuides();
}

function updateWidget(widgetId, patch, options = {}) {
  const widget = getWidget(widgetId);
  if (!widget) {
    return;
  }
  Object.assign(widget, patch);
  renderWidgetSelection();
  if (!options.live) {
    renderInspector();
  }
  renderCanvasOverlays();
  if (options.refreshPreview !== false) {
    schedulePreviewRefresh();
  }
  updateSaveButtonState();
}

function updateWidgetStyle(widgetId, key, value, options = {}) {
  const widget = getWidget(widgetId);
  if (!widget) {
    return;
  }
  widget.style = Object.assign({}, widget.style, { [key]: value });
  renderWidgetSelection();
  if (!options.live) {
    renderInspector();
  }
  renderCanvasOverlays();
  schedulePreviewRefresh();
  updateSaveButtonState();
}

function moveLayer(widgetId, delta) {
  if (!draftState) {
    return;
  }
  const widgets = getWidgetsInLayerOrder();
  const index = widgets.findIndex((widget) => widget.id === widgetId);
  const targetIndex = index + delta;
  if (index < 0 || targetIndex < 0 || targetIndex >= widgets.length) {
    return;
  }
  const [moved] = widgets.splice(index, 1);
  widgets.splice(targetIndex, 0, moved);
  widgets.forEach((widget, order) => {
    widget.z_index = (order + 1) * 10;
  });
  renderWidgetSelection();
  renderInspector();
  renderCanvasOverlays();
  schedulePreviewRefresh();
}

function beginInteraction(event, widgetId, handle) {
  if (!draftState) {
    return;
  }
  if (event.button !== undefined && event.button !== 0) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  selectedWidgetId = widgetId;
  const widget = getWidget(widgetId);
  if (!widget) {
    return;
  }
  const rect = widgetToRect(widget);
  activeInteraction = {
    widgetId,
    handle,
    startX: event.clientX,
    startY: event.clientY,
    startRect: rect,
    moved: false,
  };
  activeSnapGuides = [];
  renderSnapGuides();
  renderWidgetSelection();
  renderInspector();
  renderCanvasOverlays();
}

function resizeRect(rect, handle, dx, dy) {
  let nextRect = { ...rect };
  if (handle === "nw") {
    nextRect.left += dx;
    nextRect.top += dy;
    nextRect.width -= dx;
    nextRect.height -= dy;
  } else if (handle === "ne") {
    nextRect.top += dy;
    nextRect.width += dx;
    nextRect.height -= dy;
  } else if (handle === "sw") {
    nextRect.left += dx;
    nextRect.width -= dx;
    nextRect.height += dy;
  } else {
    nextRect.width += dx;
    nextRect.height += dy;
  }

  if (nextRect.width < MIN_WIDGET_SIZE) {
    if (handle === "nw" || handle === "sw") {
      nextRect.left -= MIN_WIDGET_SIZE - nextRect.width;
    }
    nextRect.width = MIN_WIDGET_SIZE;
  }
  if (nextRect.height < MIN_WIDGET_SIZE) {
    if (handle === "nw" || handle === "ne") {
      nextRect.top -= MIN_WIDGET_SIZE - nextRect.height;
    }
    nextRect.height = MIN_WIDGET_SIZE;
  }
  return nextRect;
}

function handlePointerMove(event) {
  if (!activeInteraction || !draftState) {
    return;
  }
  const widget = getWidget(activeInteraction.widgetId);
  if (!widget) {
    return;
  }
  const metrics = getRenderedPreviewMetrics();
  const dx = (event.clientX - activeInteraction.startX) / metrics.scaleX;
  const dy = (event.clientY - activeInteraction.startY) / metrics.scaleY;
  let nextRect = { ...activeInteraction.startRect };
  if (activeInteraction.handle) {
    nextRect = resizeRect(nextRect, activeInteraction.handle, dx, dy);
  } else {
    nextRect.left += dx;
    nextRect.top += dy;
  }
  const snapped = snapRectToGuides(nextRect, activeInteraction.widgetId, activeInteraction.handle);
  nextRect = snapped.rect;
  nextRect = clampRect(nextRect, getPreviewDimensions());
  const nextPatch = rectToWidgetPatch(widget, nextRect);
  if (
    widget.x === nextPatch.x
    && widget.y === nextPatch.y
    && widget.width === nextPatch.width
    && widget.height === nextPatch.height
  ) {
    return;
  }
  Object.assign(widget, nextPatch);
  activeInteraction.moved = true;
  activeSnapGuides = snapped.guides;
  if (previewRefreshTimer) {
    clearTimeout(previewRefreshTimer);
    previewRefreshTimer = null;
  }
  renderInspector();
  renderCanvasOverlays();
  schedulePreviewRefresh({ drag: true });
}

function endInteraction() {
  if (!activeInteraction) {
    return;
  }
  const interaction = activeInteraction;
  activeInteraction = null;
  activeSnapGuides = [];
  if (interaction.moved && (dragPreviewTimer || dragPreviewDirty)) {
    schedulePreviewRefresh({ immediate: true });
  }
  renderWidgetSelection();
  renderInspector();
  renderCanvasOverlays();
}

function openHelp() {
  const modal = elements.helpModal;
  if (!modal) {
    return;
  }
  modal.hidden = false;
  if (typeof modal.showModal === "function" && !modal.open) {
    modal.showModal();
  }
  elements.helpButton?.setAttribute("aria-expanded", "true");
}

function closeHelp() {
  const modal = elements.helpModal;
  if (!modal) {
    return;
  }
  if (typeof modal.close === "function" && modal.open) {
    modal.close();
  }
  modal.hidden = true;
  elements.helpButton?.setAttribute("aria-expanded", "false");
}

async function loadState() {
  try {
    savedState = await fetchJson("/api/state", "Failed to load HUD config");
    draftState = cloneHud(savedState.hud);
    accordionStates.browse = true;
    accordionStates.layers = true;
    accordionStates.themeDefaults = false;
    ensureSelection();
    if (elements.preview) {
      elements.preview.style.aspectRatio = `${savedState.preview.width} / ${savedState.preview.height}`;
    }
    updateSaveButtonState();
    renderPresetControls();
    renderProjectControls();
    syncAccordionPanels();
    renderOverlayLibrary();
    renderWidgetSelection();
    renderInspector();
    renderCanvasOverlays();
    updateRenderButtonState();
    await refreshPreview();
    renderRenderPreviewPane();
    return true;
  } catch (error) {
    savedState = null;
    draftState = null;
    selectedWidgetId = null;
    clearPreviewUrl();
    clearRenderPreviewPoll();
    clearRenderPreviewUrl();
    renderPreviewVersion = 0;
    if (elements.presetSelect) {
      elements.presetSelect.innerHTML = "";
    }
    if (elements.themeControls) {
      elements.themeControls.innerHTML = "";
    }
    if (elements.overlayLibraryList) {
      elements.overlayLibraryList.innerHTML = "";
    }
    if (elements.projectActivityFile) {
      elements.projectActivityFile.innerHTML = "";
    }
    if (elements.projectVideoGlobs) {
      elements.projectVideoGlobs.innerHTML = "";
    }
    if (elements.projectOutputDir) {
      elements.projectOutputDir.innerHTML = "";
    }
    if (elements.preview) {
      elements.preview.removeAttribute("src");
    }
    if (elements.widgetList) {
      elements.widgetList.innerHTML = "";
    }
    if (elements.inspectorContent) {
      elements.inspectorContent.innerHTML = "";
    }
    activeSnapGuides = [];
    toggleThemeDefaults(false);
    renderSnapGuides();
    updateSaveButtonState();
    updateRenderButtonState();
    renderRenderPreviewPane();
    setStatusMessage(readErrorMessage(error, "Failed to load HUD config"));
    return false;
  }
}

async function saveState() {
  try {
    if (!savedState || !draftState) {
      throw new Error(elements.statusMessage?.textContent || "Failed to load HUD config");
    }
    const payload = Object.assign(cloneHud(draftState), { revision: savedState.revision });
    const response = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload.error ?? "Failed to save HUD config");
    }
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "Failed to save HUD config");
    return;
  }
  setStatusMessage("Saved YAML.", "info");
  await loadState();
}

if (elements.helpButton) {
  elements.helpButton.addEventListener("click", openHelp);
}
if (elements.helpCloseButton) {
  elements.helpCloseButton.addEventListener("click", closeHelp);
}
if (elements.videoPreviewCloseButton) {
  elements.videoPreviewCloseButton.addEventListener("click", closeVideoPreview);
}
if (elements.helpModal) {
  elements.helpModal.addEventListener("click", (event) => {
    if (event.target === elements.helpModal) {
      closeHelp();
    }
  });
  elements.helpModal.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeHelp();
  });
}
if (elements.saveButton) {
  elements.saveButton.addEventListener("click", saveState);
}
if (elements.savePresetButton) {
  elements.savePresetButton.addEventListener("click", savePreset);
}
if (elements.presetSelect) {
  elements.presetSelect.addEventListener("change", (event) => {
    void selectPreset(event.target.value);
  });
}
if (elements.renderButton) {
  elements.renderButton.addEventListener("click", async () => {
    try {
      await startRenderJob();
      setStatusMessage("Render started.", "info");
    } catch (error) {
      setStatusMessage(readErrorMessage(error, "Failed to start render"));
    }
  });
}
if (elements.renderCancelButton) {
  elements.renderCancelButton.addEventListener("click", cancelRenderJob);
}
if (elements.renderMinimizeButton) {
  elements.renderMinimizeButton.addEventListener("click", () => {
    renderPanelMinimized = true;
    renderRenderPanel();
    void syncRenderPreviewState(renderState.status);
  });
}
if (elements.renderDrawerTab) {
  elements.renderDrawerTab.addEventListener("click", () => {
    renderPanelMinimized = false;
    renderRenderPanel();
    void syncRenderPreviewState(renderState.status);
  });
}
if (elements.renderPreviewToggle) {
  elements.renderPreviewToggle.addEventListener("click", async () => {
    if (renderPreviewOpen) {
      closeRenderPreview();
    } else {
      openRenderPreview();
    }
    renderRenderPreviewPane();
    await syncRenderPreviewState(renderState.status);
  });
}
if (elements.renderPreviewCloseButton) {
  elements.renderPreviewCloseButton.addEventListener("click", async () => {
    closeRenderPreview();
    renderRenderPreviewPane();
    await syncRenderPreviewState(renderState.status);
  });
}
if (elements.renderPreviewModal) {
  elements.renderPreviewModal.addEventListener("cancel", async (event) => {
    event.preventDefault();
    closeRenderPreview();
    renderRenderPreviewPane();
    await syncRenderPreviewState(renderState.status);
  });
}
if (elements.browseToggle) {
  elements.browseToggle.addEventListener("click", () => toggleAccordion("browse"));
}
if (elements.layersToggle) {
  elements.layersToggle.addEventListener("click", () => toggleAccordion("layers"));
}
if (elements.themeDefaultsToggle) {
  elements.themeDefaultsToggle.addEventListener("click", () => toggleThemeDefaults());
}
if (elements.preview) {
  elements.preview.addEventListener("load", () => {
    syncOverlayBounds();
    renderCanvasOverlays();
  });
}
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("resize", () => {
    syncOverlayBounds();
    renderCanvasOverlays();
  });
  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", endInteraction);
}
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && renderPreviewOpen) {
      event.preventDefault();
      closeRenderPreview();
      renderRenderPreviewPane();
      void syncRenderPreviewState(renderState.status);
      return;
    }
    if (event.key === "Escape" && videoPreviewOpen) {
      event.preventDefault();
      closeVideoPreview();
      return;
    }
    if (event.key === "Escape" && !elements.helpModal?.hidden) {
      closeHelp();
    }
  });
}

updateSaveButtonState();
updateRenderButtonState();
renderRenderPanel();
renderRenderPreviewPane();
syncAccordionPanels();
renderProjectControls();
renderOverlayLibrary();
void loadState();
void pollRenderStatus();
