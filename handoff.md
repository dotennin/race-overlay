# Handoff

## Current Goal

Continue RAC-6 portability work without turning the web spike into a separate product. The browser path should reuse Python-backed behavior where browser APIs are unreliable, especially video container metadata / `creation_time`.

User constraints:

- FIT is out of scope for this migration pass.
- TCX parsing is required.
- Browser-side video container `creation_time` is not reliable.
- Video metadata probing should use backend `ffprobe`.
- Users should not need to provide a backend video path.
- Optimized upload flow should try partial video upload first and fall back to full upload only when needed.

## Implemented State

### Backend

Modified:

- `src/race_overlay/editor_server.py`
- `tests/test_editor.py`

Backend now exposes upload-based video probing:

- `POST /api/video/probe-upload`
- Accepts JSON payload:

```json
{
  "name": "clip.MP4",
  "chunks": [
    { "kind": "head", "dataBase64": "..." }
  ]
}
```

Supported chunk flows:

- `head`
- `head + tail`
- `full`

Behavior:

- Header probe failure returns `202` with `nextProbe: "tail"`.
- Head/tail probe failure returns `202` with `nextProbe: "full"` and `needsFullUpload: true`.
- Full upload success returns `200` and serialized `VideoClip` metadata.
- Full upload failure returns `422`.
- Missing `creation_time` is now reported specifically as:

```text
uploaded video does not contain readable creation_time metadata
```

The older path-based endpoint still exists in backend code:

- `POST /api/video/probe`

But the UI has been changed to stop exposing backend video path controls.

### Frontend

Modified / added under `web/`:

- `web/src/runtime/videoProbeApi.ts`
- `web/src/runtime/videoProbeApi.test.ts`
- `web/src/components/RaceOverlay.tsx`
- `web/src/components/RaceOverlay.test.tsx`
- `web/src/App.tsx`
- `web/src/vite-env.d.ts`

Frontend behavior:

- Selecting a local video now automatically probes metadata through backend upload.
- Small files use full upload immediately.
- Larger files try:
  1. `head`
  2. `head + tail`
  3. `full`
- UI status strings:
  - `Probing video header...`
  - `Probing video tail...`
  - `Uploading full video for metadata...`
  - `Backend metadata ready`
- Backend video path input/button were removed from the React component.
- `App.tsx` reads:

```ts
import.meta.env.VITE_VIDEO_PROBE_BASE_URL
```

So the Vite app can target a separately running Python backend.

Frontend error handling now distinguishes unavailable upload API:

```text
Video metadata upload API returned HTTP 404; check that the backend probe server is configured
```

## Verification Already Run

After the latest UI/API changes:

```bash
cd web && npm test -- --run src/runtime/videoProbeApi.test.ts src/components/RaceOverlay.test.tsx
```

Result:

```text
2 passed, 16 tests passed
```

```bash
cd web && npm test -- --run
```

Result:

```text
6 passed, 27 tests passed
```

```bash
cd web && npm run build
```

Result:

```text
tsc --noEmit && vite build passed
```

Targeted backend regression:

```bash
PYTHONPATH=src uv run pytest -q tests/test_editor.py::test_video_probe_upload_api_reports_missing_creation_time_from_full_upload
```

Result:

```text
1 passed
```

## Verification Still Needed

The user interrupted right before the full backend verification after the latest missing-`creation_time` error handling change.

Run next:

```bash
PYTHONPATH=src uv run pytest -q tests/test_editor.py tests/test_video_probe.py tests/test_portability_contract.py
```

Then run:

```bash
git diff --check
```

Important: running `uv` has repeatedly modified `uv.lock` by adding `pytest-cov` / `coverage`. That appears to be local environment churn, not intended work. If it happens again, revert only `uv.lock` with:

```bash
git diff -- uv.lock | git apply -R
```

Do not revert `overlay.yaml`; it is user/local config.

## Current Worktree Notes

Expected dirty state includes:

- `overlay.yaml` modified: user/local change, do not touch.
- `src/race_overlay/editor_server.py` modified.
- `tests/test_editor.py` modified.
- `web/` untracked package with the React/Vite spike.
- `tests/fixtures/portability_contract.json` untracked.
- `tests/fixtures/portable_laps.tcx` untracked.
- `tests/test_portability_contract.py` untracked.
- `docs/superpowers/...` RAC-6 plan/spec files untracked.

`uv.lock` may currently be dirty if the interrupted run or later tests touched it. Check and clean as above.

## User-Facing Operation Notes

For `http://127.0.0.1:5173/`, the Vite frontend must know where the Python backend is. Start frontend with:

```bash
VITE_VIDEO_PROBE_BASE_URL=http://127.0.0.1:<backend-port> npm run dev
```

If this is not set and Vite has no `/api` proxy, video upload probe may hit the Vite server and report HTTP 404.

If backend responds:

```text
uploaded video does not contain readable creation_time metadata
```

then upload transport worked, but ffprobe did not find usable `creation_time` in the container metadata. This is an expected class of real-world video files, not necessarily an upload failure.

## Recommended Next Steps

1. Run the full backend verification listed above.
2. Clean `uv.lock` if `uv` touches it.
3. Consider adding a Vite dev proxy or a documented startup script so users do not need to remember `VITE_VIDEO_PROBE_BASE_URL`.
4. Decide whether the backend should return a metadata result without `creation_time` plus a warning, or keep treating missing `creation_time` as a hard error.
5. If keeping upload JSON/base64 for now, note that full-file fallback is memory-heavy. A future production transport should switch to multipart or streaming while preserving the same `head/tail/full` state machine.
