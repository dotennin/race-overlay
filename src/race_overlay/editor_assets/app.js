const HUD_REFERENCE_WIDTH = 1280;
const HUD_REFERENCE_HEIGHT = 720;
const MIN_WIDGET_SIZE = 24;
const PREVIEW_DEBOUNCE_MS = 120;
const PREVIEW_DRAG_THROTTLE_MS = 90;
const SUPPORTED_ANCHORS = ["top-left", "top-right", "bottom-left", "bottom-right"];
const STYLE_THEME_FALLBACKS = {
  font_family: "font_family",
  font_weight: "font_weight",
  font_size_px: "font_size_px",
  show_unit: "show_units",
};

const elements = {
  statusMessage: document.getElementById("status-message"),
  preset: document.getElementById("preset"),
  themeControls: document.getElementById("theme-controls"),
  widgetList: document.getElementById("widget-list"),
  inspectorContent: document.getElementById("inspector-content"),
  saveButton: document.getElementById("save-button"),
  helpButton: document.getElementById("help-button"),
  helpCloseButton: document.getElementById("help-close-button"),
  helpModal: document.getElementById("help-modal"),
  preview: document.getElementById("preview"),
  canvasStage: document.getElementById("canvas-stage"),
  widgetOverlays: document.getElementById("widget-overlays"),
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

function cloneHud(hud) {
  const theme = Object.assign({}, hud.theme);
  const widgets = hud.widgets.map((widget) => ({
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
  }));
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

async function fetchJson(url, fallbackMessage) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error ?? fallbackMessage);
  }
  return payload;
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
  if (!savedState || !savedState.schema || !savedState.schema.widgets) {
    return null;
  }
  return savedState.schema.widgets[widgetId] ?? null;
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

function isDraftDirty() {
  if (!savedState || !draftState) {
    return false;
  }
  return JSON.stringify(savedState.hud) !== JSON.stringify(draftState);
}

function updateSaveButtonState() {
  if (!elements.saveButton) {
    return;
  }
  elements.saveButton.disabled = !savedState || !draftState;
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
}

function renderLayers() {
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
      renderLayers();
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

    const actions = document.createElement("div");
    actions.className = "layer-item__actions";

    const visibilityButton = document.createElement("button");
    visibilityButton.type = "button";
    visibilityButton.className = `visibility-toggle${widget.visible ? "" : " is-off"}`;
    visibilityButton.title = widget.visible ? "Hide widget" : "Show widget";
    visibilityButton.textContent = widget.visible ? "◉" : "○";
    visibilityButton.addEventListener("click", () => {
      updateWidget(widget.id, { visible: !widget.visible });
    });
    actions.appendChild(visibilityButton);

    const upButton = document.createElement("button");
    upButton.type = "button";
    upButton.className = "layer-control";
    upButton.textContent = "▲";
    upButton.title = "Bring forward";
    upButton.addEventListener("click", () => moveLayer(widget.id, 1));
    actions.appendChild(upButton);

    const downButton = document.createElement("button");
    downButton.type = "button";
    downButton.className = "layer-control";
    downButton.textContent = "▼";
    downButton.title = "Send backward";
    downButton.addEventListener("click", () => moveLayer(widget.id, -1));
    actions.appendChild(downButton);

    item.appendChild(actions);
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

function buildTextInput(value, onChange, type = "text") {
  const input = document.createElement("input");
  input.type = type;
  input.value = value ?? "";
  input.addEventListener("change", () => onChange(input.value));
  return input;
}

function buildNumberInput(value, onChange, options = {}) {
  const input = document.createElement("input");
  input.type = "number";
  input.value = String(value);
  input.step = String(options.step ?? 1);
  if (options.min !== undefined) {
    input.min = String(options.min);
  }
  if (options.max !== undefined) {
    input.max = String(options.max);
  }
  input.addEventListener("change", () => {
    if (input.value.trim() === "") {
      input.value = String(value);
      return;
    }
    const nextValue = Number(input.value);
    if (!Number.isFinite(nextValue) || !Number.isInteger(nextValue)) {
      input.value = String(value);
      return;
    }
    onChange(nextValue);
  });
  return input;
}

function buildCheckbox(value, onChange) {
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(value);
  input.addEventListener("change", () => onChange(input.checked));
  return input;
}

function buildSelectInput(value, options, onChange) {
  const select = document.createElement("select");
  options.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue;
    option.selected = optionValue === value;
    select.appendChild(option);
  });
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function buildRgbaInput(value, onChange) {
  const values = Array.isArray(value) && value.length === 4 ? value : [0, 0, 0, 255];
  const wrapper = document.createElement("div");
  wrapper.className = "rgba-input";
  ["R", "G", "B", "A"].forEach((channelLabel, index) => {
    const channel = document.createElement("label");
    channel.className = "rgba-input__channel";
    const text = document.createElement("span");
    text.textContent = channelLabel;
    channel.appendChild(text);
    channel.appendChild(
      buildNumberInput(values[index], (nextValue) => {
        const nextChannels = [...values];
        nextChannels[index] = nextValue;
        onChange(nextChannels);
      }, { min: 0, max: 255 }),
    );
    wrapper.appendChild(channel);
  });
  return wrapper;
}

function renderFieldControl(parent, key, metadata, value, onChange) {
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
    appendField(parent, fieldLabel, buildRgbaInput(value, onChange), true);
    return;
  }
  if (metadata?.kind === "enum") {
    appendField(parent, fieldLabel, buildSelectInput(value, metadata.options ?? [], onChange), true);
    return;
  }
  if (metadata?.kind === "integer" || typeof value === "number") {
    appendField(parent, fieldLabel, buildNumberInput(value, onChange, { min: metadata?.min }), false);
    return;
  }
  appendField(parent, fieldLabel, buildTextInput(String(value ?? ""), onChange), true);
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
    renderFieldControl(themeGrid, key, metadata, draftState.theme[key], (nextValue) => {
      if (!draftState) {
        return;
      }
      draftState.theme = Object.assign({}, draftState.theme, { [key]: nextValue });
      renderThemeControls();
      renderInspector();
      schedulePreviewRefresh();
      updateSaveButtonState();
    });
  });
  themeCard.appendChild(themeGrid);
  elements.themeControls.appendChild(themeCard);
}

function getStyleFieldValue(widget, key) {
  if (Object.prototype.hasOwnProperty.call(widget.style, key)) {
    return widget.style[key];
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
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Load a HUD document to inspect widgets.";
    elements.inspectorContent.appendChild(empty);
    return;
  }

  if (elements.preset) {
    elements.preset.value = draftState.preset;
  }
  renderThemeControls();

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

  const anchorSelect = document.createElement("select");
  SUPPORTED_ANCHORS.forEach((anchor) => {
    const option = document.createElement("option");
    option.value = anchor;
    option.textContent = anchor;
    option.selected = anchor === widget.anchor;
    anchorSelect.appendChild(option);
  });
  anchorSelect.addEventListener("change", () => updateWidget(widget.id, { anchor: anchorSelect.value }));
  appendField(geometryGrid, "Anchor", anchorSelect, true);
  appendField(geometryGrid, "X", buildNumberInput(widget.x, (value) => updateWidget(widget.id, { x: value })), false);
  appendField(geometryGrid, "Y", buildNumberInput(widget.y, (value) => updateWidget(widget.id, { y: value })), false);
  appendField(geometryGrid, "Width", buildNumberInput(widget.width, (value) => updateWidget(widget.id, { width: value })), false);
  appendField(geometryGrid, "Height", buildNumberInput(widget.height, (value) => updateWidget(widget.id, { height: value })), false);
  appendField(geometryGrid, "Z index", buildNumberInput(widget.z_index, (value) => updateWidget(widget.id, { z_index: value })), true);

  geometryCard.appendChild(geometryGrid);
  elements.inspectorContent.appendChild(geometryCard);

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
      renderFieldControl(styleGrid, key, styleSchema[key], getStyleFieldValue(widget, key), (nextValue) => {
        updateWidgetStyle(widget.id, key, nextValue);
      });
    });
    styleCard.appendChild(styleGrid);
  }
  elements.inspectorContent.appendChild(styleCard);
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

    const label = document.createElement("div");
    label.className = "widget-overlay__label";
    label.textContent = widget.style.label || widget.id;
    overlay.appendChild(label);

    ["nw", "ne", "sw", "se"].forEach((handleName) => {
      const handle = document.createElement("div");
      handle.className = "widget-overlay__handle";
      handle.dataset.handle = handleName;
      handle.addEventListener("pointerdown", (event) => beginInteraction(event, widget.id, handleName));
      overlay.appendChild(handle);
    });

    elements.widgetOverlays.appendChild(overlay);
  });
}

function updateWidget(widgetId, patch, options = {}) {
  const widget = getWidget(widgetId);
  if (!widget) {
    return;
  }
  Object.assign(widget, patch);
  renderLayers();
  renderInspector();
  renderCanvasOverlays();
  if (options.refreshPreview !== false) {
    schedulePreviewRefresh();
  }
  updateSaveButtonState();
}

function updateWidgetStyle(widgetId, key, value) {
  const widget = getWidget(widgetId);
  if (!widget) {
    return;
  }
  widget.style = Object.assign({}, widget.style, { [key]: value });
  renderLayers();
  renderInspector();
  renderCanvasOverlays();
  schedulePreviewRefresh();
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
  renderLayers();
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
  renderLayers();
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
  if (interaction.moved && (dragPreviewTimer || dragPreviewDirty)) {
    schedulePreviewRefresh({ immediate: true });
  }
  renderLayers();
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
    ensureSelection();
    if (elements.preview) {
      elements.preview.style.aspectRatio = `${savedState.preview.width} / ${savedState.preview.height}`;
    }
    updateSaveButtonState();
    renderLayers();
    renderInspector();
    renderCanvasOverlays();
    await refreshPreview();
    return true;
  } catch (error) {
    savedState = null;
    draftState = null;
    selectedWidgetId = null;
    clearPreviewUrl();
    if (elements.preset) {
      elements.preset.value = "";
    }
    if (elements.themeControls) {
      elements.themeControls.innerHTML = "";
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
    updateSaveButtonState();
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
    if (event.key === "Escape" && !elements.helpModal?.hidden) {
      closeHelp();
    }
  });
}

updateSaveButtonState();
void loadState();
