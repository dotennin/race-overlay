let currentState = null;

function setStatusMessage(message) {
  const status = document.getElementById("status-message");
  status.textContent = message;
  status.hidden = !message;
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

function createField(label, type, value, widgetId, fieldName) {
  const wrapper = document.createElement("label");
  wrapper.className = "field";

  const text = document.createElement("span");
  text.textContent = label;
  wrapper.appendChild(text);

  const input = document.createElement("input");
  input.type = type;
  input.dataset.widgetId = widgetId;
  input.dataset.field = fieldName;
  if (type === "checkbox") {
    input.checked = Boolean(value);
  } else {
    input.value = value;
  }
  wrapper.appendChild(input);
  return wrapper;
}

function renderWidgetList(widgets) {
  const container = document.getElementById("widget-list");
  container.innerHTML = "";

  widgets.forEach((widget) => {
    const card = document.createElement("section");
    card.className = "widget-card";

    const title = document.createElement("h3");
    title.textContent = `${widget.id} (${widget.type})`;
    card.appendChild(title);

    card.appendChild(createField("Visible", "checkbox", widget.visible, widget.id, "visible"));
    card.appendChild(createField("Anchor", "text", widget.anchor, widget.id, "anchor"));
    card.appendChild(createField("X", "number", widget.x, widget.id, "x"));
    card.appendChild(createField("Y", "number", widget.y, widget.id, "y"));
    card.appendChild(createField("Width", "number", widget.width, widget.id, "width"));
    card.appendChild(createField("Height", "number", widget.height, widget.id, "height"));
    card.appendChild(createField("Z index", "number", widget.z_index, widget.id, "z_index"));
    card.appendChild(
      createField("Label", "text", widget.style?.label ?? "", widget.id, "style.label"),
    );

    container.appendChild(card);
  });
}

function widgetInputValue(input) {
  if (input.type === "checkbox") {
    return input.checked;
  }
  if (input.type === "number") {
    if (input.value.trim() === "") {
      throw new Error(`${input.dataset.field} must be a whole number`);
    }
    const value = Number(input.value);
    if (!Number.isFinite(value) || !Number.isInteger(value)) {
      throw new Error(`${input.dataset.field} must be a whole number`);
    }
    return value;
  }
  return input.value;
}

function collectEditorPayload() {
  const widgets = currentState.hud.widgets.map((widget) => ({
    ...widget,
    bindings: { ...widget.bindings },
    style: { ...widget.style },
  }));

  document.querySelectorAll("[data-widget-id]").forEach((input) => {
    const widget = widgets.find((item) => item.id === input.dataset.widgetId);
    if (!widget) {
      return;
    }

    const value = widgetInputValue(input);
    if (input.dataset.field === "style.label") {
      widget.style.label = value;
      return;
    }
    widget[input.dataset.field] = value;
  });

  return {
    preset: document.getElementById("preset").value,
    theme: {
      ...currentState.hud.theme,
      note_text: document.getElementById("note-text").value,
    },
    widgets,
  };
}

async function loadState() {
  const saveButton = document.getElementById("save-button");
  try {
    currentState = await fetchJson("/api/state", "Failed to load HUD config");
    document.getElementById("preset").value = currentState.hud.preset;
    document.getElementById("note-text").value = currentState.hud.theme.note_text ?? "";
    document.getElementById("preview").src = `/api/preview.png?cache=${Date.now()}`;
    renderWidgetList(currentState.hud.widgets);
    saveButton.disabled = false;
    setStatusMessage("");
    return true;
  } catch (error) {
    currentState = null;
    document.getElementById("preset").value = "";
    document.getElementById("note-text").value = "";
    document.getElementById("preview").removeAttribute("src");
    renderWidgetList([]);
    saveButton.disabled = true;
    setStatusMessage(readErrorMessage(error, "Failed to load HUD config"));
    return false;
  }
}

async function saveState() {
  try {
    if (!currentState) {
      throw new Error(
        document.getElementById("status-message").textContent || "Failed to load HUD config",
      );
    }
    const payload = collectEditorPayload();
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
  await loadState();
}

document.getElementById("save-button").addEventListener("click", saveState);
void loadState();
