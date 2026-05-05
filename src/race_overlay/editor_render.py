from dataclasses import dataclass, field
from datetime import datetime, timezone
from inspect import signature
from threading import Event, Lock, Thread
from typing import Callable
from uuid import uuid4


ProgressReporter = Callable[[str], None]
SnapshotBuilder = Callable[[dict[str, object]], object]
PipelineRunner = Callable[..., None]


@dataclass(slots=True)
class RenderJobState:
    job_id: str | None = None
    status: str = "idle"
    stage: str = ""
    cancel_requested: bool = False
    clip_name: str | None = None
    frame_index: int | None = None
    frame_total: int | None = None
    percent: int | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    preview_enabled: bool = False
    preview_available: bool = False
    preview_seq: int = 0
    preview_updated_at: str | None = None


@dataclass(slots=True, frozen=True)
class RenderProgressUpdate:
    phase: str
    message: str = ""
    clip_name: str | None = None
    frame_index: int | None = None
    frame_total: int | None = None
    percent: int | None = None


@dataclass(slots=True, frozen=True)
class RenderPreviewUpdate:
    clip_name: str
    frame_index: int
    frame_time_seconds: float
    image_bytes: bytes


class RenderJobAlreadyRunningError(RuntimeError):
    """Raised when the editor render queue already has an active job."""


class RenderJobCanceledError(RuntimeError):
    """Raised when an active render job is canceled."""


class RenderPreviewToggleInactiveError(RuntimeError):
    """Raised when preview is enabled without an active render."""


class EditorRenderJobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cancel_requested = Event()
        self._state = RenderJobState()
        self._preview_image: bytes | None = None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, object]:
        return {
            "job_id": self._state.job_id,
            "status": self._state.status,
            "stage": self._state.stage,
            "cancel_requested": self._state.cancel_requested,
            "clip_name": self._state.clip_name,
            "frame_index": self._state.frame_index,
            "frame_total": self._state.frame_total,
            "percent": self._state.percent,
            "logs": list(self._state.logs),
            "error": self._state.error,
            "started_at": self._state.started_at,
            "finished_at": self._state.finished_at,
            "preview": {
                "enabled": self._state.preview_enabled,
                "available": self._state.preview_available,
                "version": self._state.preview_seq,
                "updated_at": self._state.preview_updated_at,
            },
        }

    def start(self, payload: dict[str, object], *, build_snapshot: SnapshotBuilder, run_pipeline: PipelineRunner) -> dict[str, object]:
        with self._lock:
            if self._state.status == "running":
                raise RenderJobAlreadyRunningError("render already in progress")
            self._cancel_requested.clear()
            self._preview_image = None
            self._state = RenderJobState(
                job_id=uuid4().hex,
                status="running",
                stage="Starting render",
                cancel_requested=False,
                clip_name=None,
                frame_index=None,
                frame_total=None,
                percent=None,
                logs=[],
                error=None,
                started_at=_now_iso(),
                finished_at=None,
                preview_enabled=False,
                preview_available=False,
                preview_seq=0,
                preview_updated_at=None,
            )

        thread = Thread(
            target=self._run_job,
            args=(payload, build_snapshot, run_pipeline),
            daemon=True,
        )
        thread.start()
        return self.snapshot()

    def _run_job(self, payload: dict[str, object], build_snapshot: SnapshotBuilder, run_pipeline: PipelineRunner) -> None:
        try:
            with build_snapshot(payload) as snapshot_path:
                kwargs: dict[str, object] = {"progress": self._append_log}
                if "progress_update" in signature(run_pipeline).parameters:
                    kwargs["progress_update"] = self._append_progress
                if "preview_update" in signature(run_pipeline).parameters:
                    kwargs["preview_update"] = self.update_preview
                if "cancel_requested" in signature(run_pipeline).parameters:
                    kwargs["cancel_requested"] = self._cancel_requested.is_set
                run_pipeline(snapshot_path, **kwargs)
        except RenderJobCanceledError as exc:
            self._finish_canceled(str(exc))
            return
        except Exception as exc:
            self._finish_failed(str(exc))
            return
        self._finish_succeeded()

    def cancel(self) -> dict[str, object]:
        with self._lock:
            if self._state.status != "running":
                raise ValueError("no render is currently running")
            self._cancel_requested.set()
            self._state.cancel_requested = True
            self._state.stage = "Cancel requested"
        return self.snapshot()

    def set_preview_enabled(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            if not enabled and self._state.status != "running":
                self._state.preview_enabled = False
                return self._snapshot_locked()
            if self._state.status != "running":
                raise RenderPreviewToggleInactiveError("no render is currently running")
            self._state.preview_enabled = enabled
            return self._snapshot_locked()

    def update_preview(self, payload: RenderPreviewUpdate | bytes | None) -> bool:
        with self._lock:
            if self._state.status != "running" or not self._state.preview_enabled:
                return False
            if payload is None:
                return True
            if isinstance(payload, RenderPreviewUpdate):
                preview_image = payload.image_bytes
            else:
                preview_image = bytes(payload)
            self._preview_image = bytes(preview_image)
            self._state.preview_available = True
            self._state.preview_seq += 1
            self._state.preview_updated_at = _now_iso()
            return True

    def latest_preview(self) -> bytes | None:
        with self._lock:
            if self._preview_image is None:
                return None
            return bytes(self._preview_image)

    def _append_log(self, message: str) -> None:
        with self._lock:
            self._state.logs.append(message)
            if len(self._state.logs) > 500:
                self._state.logs = self._state.logs[-500:]
            self._state.stage = message

    def _append_progress(self, update: RenderProgressUpdate) -> None:
        with self._lock:
            self._state.stage = update.message or update.phase
            self._state.clip_name = update.clip_name
            self._state.frame_index = update.frame_index
            self._state.frame_total = update.frame_total
            self._state.percent = update.percent
            if update.message:
                self._state.logs.append(update.message)
                if len(self._state.logs) > 500:
                    self._state.logs = self._state.logs[-500:]

    def _finish_succeeded(self) -> None:
        with self._lock:
            self._state.status = "succeeded"
            self._state.finished_at = _now_iso()
            self._state.preview_enabled = False
            if not self._state.stage:
                self._state.stage = "Render completed"

    def _finish_canceled(self, error: str) -> None:
        with self._lock:
            self._state.status = "canceled"
            self._state.error = error
            self._state.finished_at = _now_iso()
            self._state.cancel_requested = True
            self._state.preview_enabled = False

    def _finish_failed(self, error: str) -> None:
        with self._lock:
            self._state.status = "failed"
            self._state.error = error
            self._state.finished_at = _now_iso()
            self._state.preview_enabled = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
