# Editor Overlay Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a left-side overlay library that can append every supported HUD widget from the editor, while making Theme defaults collapsed by default in the Inspector.

**Architecture:** Keep the editor schema-driven for widget/theme fields, but add a dedicated editor-side overlay catalog with insertion defaults. The shell becomes a three-column layout: add-overlay rail, canvas, and inspector. Theme defaults become a presentational accordion in the inspector, with no change to saved HUD data.

**Tech Stack:** Python, Typer editor server, schema payload generation in `editor_preview.py`, vanilla JS in `editor_assets/app.js`, HTML/CSS in `editor_assets/index.html` and `styles.css`, pytest, agent-browser for visual verification.

---

## File map

- Modify: `src/race_overlay/editor_preview.py`
  - Add overlay catalog metadata and insertion defaults to the editor state payload.
- Modify: `src/race_overlay/editor_assets/index.html`
  - Add left-rail container for overlay library and accordion shell for Theme defaults.
- Modify: `src/race_overlay/editor_assets/styles.css`
  - Expand the editor shell to three columns and style the library rail / accordion states.
- Modify: `src/race_overlay/editor_assets/app.js`
  - Render overlay library, append widgets from catalog defaults, manage theme accordion state, keep selection/preview/save behavior intact.
- Modify: `tests/test_editor.py`
  - Cover catalog payload shape, supported widget coverage including `lap_waterfall`, and static editor HTML response expectations.
- Optional modify: `README.md`
  - Only if a short editor capability note is needed after implementation.

### Task 1: Add overlay catalog payload from Python

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing editor-state test for the overlay catalog**

```python
def test_build_editor_state_exposes_overlay_library_with_lap_waterfall() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    catalog = state["overlay_library"]
    widget_types = {item["type"] for item in catalog}

    assert "lap_waterfall" in widget_types
    assert "progress_bar" in widget_types
    assert "route_map" in widget_types
    lap_entry = next(item for item in catalog if item["type"] == "lap_waterfall")
    assert lap_entry["defaults"]["bindings"] == {"value": "laps"}
    assert lap_entry["defaults"]["style"]["visible_rows"] == 5
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest -q tests/test_editor.py::test_build_editor_state_exposes_overlay_library_with_lap_waterfall`

Expected: FAIL because `build_editor_state()` does not yet expose `overlay_library`.

- [ ] **Step 3: Add a catalog builder with per-widget defaults**

```python
def _overlay_library() -> list[dict[str, object]]:
    return [
        {
            "type": "progress_bar",
            "label": "Distance ruler",
            "defaults": {
                "id": "distance-ruler",
                "type": "progress_bar",
                "bindings": {"value": "distance_m"},
                "anchor": "bottom-left",
                "x": 40,
                "y": 56,
                "width": 420,
                "height": 72,
                "z_index": 10,
                "visible": True,
                "style": {"label": "Distance", "variant": "ruler"},
            },
        },
        {
            "type": "lap_waterfall",
            "label": "Lap waterfall",
            "defaults": {
                "id": "lap-waterfall",
                "type": "lap_waterfall",
                "bindings": {"value": "laps"},
                "anchor": "bottom-right",
                "x": 40,
                "y": 120,
                "width": 420,
                "height": 220,
                "z_index": 30,
                "visible": True,
                "style": {"visible_rows": 5},
            },
        },
    ]


def build_editor_state(config: ProjectConfig, width: int, height: int) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "schema": _build_editor_schema(config.hud),
        "overlay_library": _overlay_library(),
        "revision": _hud_revision(config.hud),
        "preview": {"width": width, "height": height, "route_points": _sample_route_points()},
    }
```

- [ ] **Step 4: Add normalization helpers so inserted IDs are unique**

```python
def _unique_overlay_id(base_id: str, hud: HudConfig) -> str:
    existing = {widget.id for widget in hud.widgets}
    if base_id not in existing:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in existing:
        suffix += 1
    return f"{base_id}-{suffix}"
```

Use this helper from the catalog path if the payload needs to be regenerated with the current HUD context instead of a fixed static list.

- [ ] **Step 5: Run the focused editor tests**

Run: `uv run pytest -q tests/test_editor.py -k "overlay_library or lap_waterfall_schema"`

Expected: PASS with catalog coverage and existing lap-waterfall schema coverage intact.

- [ ] **Step 6: Commit**

```bash
git add src/race_overlay/editor_preview.py tests/test_editor.py
git commit -m "feat: expose editor overlay library"
```

### Task 2: Reshape the editor shell and add a theme accordion

**Files:**
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing HTML response test for the new shell**

```python
def test_editor_server_serves_overlay_library_and_theme_toggle(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        response, body = fetch_editor_page(base_url)

    assert response.status == 200
    assert 'id="overlay-library"' in body
    assert 'id="theme-defaults-toggle"' in body
    assert 'id="theme-defaults-panel"' in body
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest -q tests/test_editor.py::test_editor_server_serves_overlay_library_and_theme_toggle`

Expected: FAIL because the current HTML exposes only canvas + inspector.

- [ ] **Step 3: Update the HTML shell**

```html
<div id="app-shell">
  <aside id="overlay-library-panel">
    <div class="panel-header">
      <p class="eyebrow">Add overlay</p>
      <h2>Overlay library</h2>
      <p class="panel-copy">Append any supported HUD block</p>
    </div>
    <div id="overlay-library"></div>
  </aside>

  <main id="canvas-panel">...</main>

  <aside id="inspector-panel">
    ...
    <section class="panel-section panel-section--accordion">
      <button id="theme-defaults-toggle" type="button" aria-expanded="false" aria-controls="theme-defaults-panel">
        <span>Theme defaults</span>
      </button>
      <div id="theme-defaults-panel" hidden>
        <div id="theme-controls"></div>
      </div>
    </section>
    <div id="inspector-content"></div>
  </aside>
</div>
```

- [ ] **Step 4: Update layout and accordion styling**

```css
#app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 360px;
  gap: 16px;
  padding: 16px;
  align-items: start;
}

#overlay-library-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px;
  border: 1px solid var(--panel-border);
  border-radius: 22px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

#theme-defaults-panel[hidden] {
  display: none;
}
```

- [ ] **Step 5: Preserve mobile stacking**

```css
@media (max-width: 1180px) {
  #app-shell {
    grid-template-columns: 240px minmax(0, 1fr) 320px;
  }
}

@media (max-width: 900px) {
  #app-shell {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run the focused server/UI tests**

Run: `uv run pytest -q tests/test_editor.py -k "editor_server_serves_overlay_library_and_theme_toggle or editor_http_endpoint"`

Expected: PASS with the new shell elements present in served HTML.

- [ ] **Step 7: Commit**

```bash
git add src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: add editor overlay rail shell"
```

### Task 3: Wire overlay insertion and accordion behavior in app.js

**Files:**
- Modify: `src/race_overlay/editor_assets/app.js`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing editor-state serialization test for inserted widgets**

```python
def test_save_editor_payload_accepts_inserted_lap_waterfall_widget(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    editor_state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = json.loads(json.dumps(editor_state["hud"]))
    payload["revision"] = editor_state["revision"]
    payload["widgets"].append(
        {
            "id": "lap-waterfall",
            "type": "lap_waterfall",
            "bindings": {"value": "laps"},
            "anchor": "bottom-right",
            "x": 40,
            "y": 120,
            "width": 420,
            "height": 220,
            "z_index": 30,
            "visible": True,
            "style": {"visible_rows": 5},
        }
    )

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert any(widget.id == "lap-waterfall" and widget.type == "lap_waterfall" for widget in reloaded.hud.widgets)
```

- [ ] **Step 2: Run the focused test to verify it fails if defaults/payload shape are wrong**

Run: `uv run pytest -q tests/test_editor.py::test_save_editor_payload_accepts_inserted_lap_waterfall_widget`

Expected: FAIL until the insertion defaults and complete payload shape match what the editor emits.

- [ ] **Step 3: Render the overlay library from payload**

```javascript
function renderOverlayLibrary() {
  const container = elements.overlayLibrary;
  if (!container || !savedState) return;
  container.innerHTML = "";
  (savedState.overlay_library ?? []).forEach((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "overlay-library-item";
    button.textContent = entry.label;
    button.addEventListener("click", () => appendOverlayFromLibrary(entry));
    container.appendChild(button);
  });
}
```

- [ ] **Step 4: Append a widget immediately and select it**

```javascript
function appendOverlayFromLibrary(entry) {
  if (!draftState) return;
  const nextWidget = structuredClone(entry.defaults);
  nextWidget.id = nextOverlayId(nextWidget.id);
  nextWidget.z_index = nextZIndex();
  draftState.widgets = [...draftState.widgets, nextWidget];
  selectedWidgetId = nextWidget.id;
  renderWidgetList();
  renderInspector();
  renderCanvasOverlays();
  schedulePreviewRefresh();
  updateSaveButtonState();
}
```

- [ ] **Step 5: Add theme accordion state**

```javascript
let themeDefaultsExpanded = false;

function renderThemeControls() {
  const panel = elements.themeDefaultsPanel;
  const toggle = elements.themeDefaultsToggle;
  if (!panel || !toggle) return;
  panel.hidden = !themeDefaultsExpanded;
  toggle.setAttribute("aria-expanded", themeDefaultsExpanded ? "true" : "false");
  if (!themeDefaultsExpanded) {
    elements.themeControls.innerHTML = "";
    return;
  }
  // existing schema-backed field rendering stays here
}
```

Bind:

```javascript
elements.themeDefaultsToggle?.addEventListener("click", () => {
  themeDefaultsExpanded = !themeDefaultsExpanded;
  renderThemeControls();
});
```

- [ ] **Step 6: Update initialization flow**

```javascript
function applyState(state) {
  savedState = state;
  draftState = cloneHud(state.hud);
  ensureSelection();
  renderOverlayLibrary();
  renderWidgetList();
  renderThemeControls();
  renderInspector();
  refreshPreview();
}
```

- [ ] **Step 7: Run editor tests**

Run: `uv run pytest -q tests/test_editor.py`

Expected: PASS with inserted-widget payloads, HTML contract tests, and existing save/preview tests all green.

- [ ] **Step 8: Manual browser verification with agent-browser**

Run:

```bash
uv run race-overlay edit-hud --config-path overlay.yaml
agent-browser batch "open http://localhost:8000" "snapshot -i"
```

Then verify:
- left overlay rail is visible,
- clicking `lap_waterfall` adds a widget,
- new widget is selected immediately,
- Theme defaults starts collapsed and expands only when clicked.

- [ ] **Step 9: Commit**

```bash
git add src/race_overlay/editor_assets/app.js tests/test_editor.py
git commit -m "feat: add overlay library interactions"
```

### Task 4: Final polish and regression pass

**Files:**
- Modify: `README.md` (only if needed)
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Add or update a short README editor note if the UI changed materially**

```markdown
- The HUD editor now includes an overlay library for adding supported widgets, and theme defaults stay collapsed until expanded.
```

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS with the full repository test suite green.

- [ ] **Step 3: Capture final visual check**

Run:

```bash
agent-browser batch "open http://localhost:8000" "screenshot"
```

Expected: screenshot clearly shows the left overlay rail and collapsed theme defaults.

- [ ] **Step 4: Commit**

```bash
git add README.md tests/test_editor.py
git commit -m "docs: update editor overlay library notes"
```
