# Render Cancel and Live Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cancel button with confirmation to the editor render flow and expose live, structured render progress while a job is running.

**Architecture:** Keep the current polling-based editor API, but extend render job state with a cancel flag and structured progress fields. The pipeline will emit fine-grained progress updates during clip/frame processing and check for cancellation between frames so the current job can stop quickly while leaving partial output intact.

**Tech Stack:** Python 3.12, stdlib HTTP server, Typer CLI, browser DOM/Fetch, pytest.

---

### Task 1: Add cancelable render job state

**Files:**
- Modify: `src/race_overlay/editor_render.py`
- Modify: `src/race_overlay/editor_server.py`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
@dataclass(slots=True)
class RenderProgressUpdate:
    phase: str
    clip_name: str | None = None
    frame_index: int | None = None
    frame_total: int | None = None
    percent: int | None = None
    message: str = ""

def test_api_render_cancel_marks_job_canceled(tmp_path, monkeypatch):
    ...
    def blocking_run_pipeline(snapshot_path, only=None, *, progress=None, progress_update=None, cancel_requested=None):
        if progress_update is not None:
            progress_update(RenderProgressUpdate(
                phase="rendering",
                clip_name="clip-a.MP4",
                frame_index=1,
                frame_total=100,
                percent=1,
                message="Rendering frame 1/100",
            ))
        release_render.wait(timeout=5)
    ...
    POST /api/render
    POST /api/render/cancel
    poll GET /api/render until status != "running"
    assert status["status"] == "canceled"
    assert status["cancel_requested"] is True
    assert status["clip_name"] == "clip-a.MP4"
    assert status["percent"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_editor.py -k 'api_render_cancel_marks_job_canceled'`
Expected: FAIL because `/api/render/cancel` and cancel state are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
from threading import Event

@dataclass(slots=True)
class RenderJobState:
    job_id: str | None = None
    status: str = "idle"
    phase: str = ""
    clip_name: str | None = None
    frame_index: int | None = None
    frame_total: int | None = None
    percent: int | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    started_at: str | None = None
    finished_at: str | None = None

class RenderJobCanceledError(RuntimeError):
    pass

def cancel(self) -> dict[str, object]:
    with self._lock:
        if self._state.status != "running":
            raise ValueError("no render is currently running")
        self._cancel_requested.set()
        self._state.cancel_requested = True
        self._state.phase = "Cancel requested"
        return self.snapshot()

def _append_progress(self, update: RenderProgressUpdate) -> None:
    ...
```

```python
if request_path == "/api/render/cancel":
    try:
        state = _RENDER_JOB_MANAGER.cancel()
    except ValueError as exc:
        self._write_json(409, {"error": str(exc)})
        return
    self._write_json(200, state)
    return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_editor.py -k 'api_render_cancel_marks_job_canceled'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_render.py src/race_overlay/editor_server.py tests/test_editor.py
git commit -m "feat: add cancelable render jobs"
```

### Task 2: Emit structured live progress from the pipeline

**Files:**
- Modify: `src/race_overlay/pipeline.py`
- Modify: `src/race_overlay/editor_render.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
def test_run_pipeline_emits_frame_progress_updates(tmp_path, monkeypatch):
    ...
    updates = []
    run_pipeline(config_path, progress=messages.append, progress_update=updates.append)
    assert updates
    assert updates[0].clip_name == "clip-a.MP4"
    assert updates[-1].percent == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_pipeline.py -k 'emits_frame_progress_updates'`
Expected: FAIL because `run_pipeline()` does not accept structured progress updates yet.

- [ ] **Step 3: Write minimal implementation**

```python
ProgressReporter = Callable[[str], None]
ProgressUpdateReporter = Callable[[RenderProgressUpdate], None]

def run_pipeline(..., progress: ProgressReporter | None = None, progress_update: ProgressUpdateReporter | None = None, cancel_requested: Callable[[], bool] | None = None) -> None:
    ...
    for index in range(_frame_count(clip)):
        if cancel_requested is not None and cancel_requested():
            raise RenderJobCanceledError("render canceled")
        if progress_update is not None:
            progress_update(RenderProgressUpdate(
                phase="rendering",
                clip_name=clip.path.name,
                frame_index=index + 1,
                frame_total=frame_total,
                percent=int(((index + 1) / frame_total) * 100),
                message=f"Rendering {clip.path.name} frame {index + 1}/{frame_total}",
            ))
```

```python
def _render_clip_streaming(..., cancel_requested=None, progress_update=None) -> None:
    ...
    if cancel_requested is not None and cancel_requested():
        _cleanup_stream_process(process)
        raise RenderJobCanceledError("render canceled")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_pipeline.py -k 'emits_frame_progress_updates'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/pipeline.py src/race_overlay/editor_render.py tests/test_pipeline.py
git commit -m "feat: stream render progress updates"
```

### Task 3: Add cancel button and live progress UI

**Files:**
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editor_assets_expose_render_cancel_and_progress_controls():
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    assert 'id="render-cancel-button"' in html
    assert 'id="render-progress"' in html
    assert 'window.confirm("Cancel current render? Partial output will be kept.")' in app_js
    assert 'POST",\n    "/api/render/cancel"' in app_js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_editor.py -k 'render_cancel_and_progress_controls'`
Expected: FAIL because the cancel UI and API call are not wired yet.

- [ ] **Step 3: Write minimal implementation**

```html
<button id="render-button" type="button">Render</button>
<button id="render-cancel-button" type="button" hidden>Cancel</button>
<progress id="render-progress" max="100" value="0"></progress>
```

```javascript
async function cancelRenderJob() {
  if (!window.confirm("Cancel current render? Partial output will be kept.")) {
    return;
  }
  const response = await fetch("/api/render/cancel", { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "Failed to cancel render");
  }
  renderState = payload;
  renderRenderPanel();
}

function renderRenderPanel() {
  ...
  elements.renderCancelButton.hidden = renderState.status !== "running";
  elements.renderProgress.value = renderState.percent ?? 0;
  elements.renderProgress.textContent = `${renderState.percent ?? 0}%`;
  elements.renderStage.textContent = [
    renderState.phase,
    renderState.clip_name ? `Current video: ${renderState.clip_name}` : null,
  ].filter(Boolean).join(" • ");
}
```

```css
#render-progress { width: 100%; }
#render-cancel-button { align-self: start; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_editor.py -k 'render_cancel_and_progress_controls'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/app.js src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: show live render progress and cancel button"
```

### Task 4: Verify cancel preserves partial output and full-suite regression

**Files:**
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_api_render_cancel_keeps_partial_outputs(tmp_path, monkeypatch):
    ...
    assert final_status["status"] == "canceled"
    assert final_status["finished_at"] is not None
    assert output_dir.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_editor.py -k 'keeps_partial_outputs'`
Expected: FAIL until cancellation path and partial-output behavior are wired through the job manager.

- [ ] **Step 3: Write minimal implementation**

```python
if cancel_requested is not None and cancel_requested():
    raise RenderJobCanceledError("render canceled")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_editor.py -k 'keeps_partial_outputs or api_render_cancel_marks_job_canceled or render_cancel_and_progress_controls'`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS with no regressions.

- [ ] **Step 6: Commit**

```bash
git add tests/test_editor.py
git commit -m "test: cover render cancellation and partial output handling"
```
