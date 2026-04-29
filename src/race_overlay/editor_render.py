from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock, Thread
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
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RenderJobAlreadyRunningError(RuntimeError):
    """Raised when the editor render queue already has an active job."""


class EditorRenderJobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._state = RenderJobState()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "job_id": self._state.job_id,
                "status": self._state.status,
                "stage": self._state.stage,
                "logs": list(self._state.logs),
                "error": self._state.error,
                "started_at": self._state.started_at,
                "finished_at": self._state.finished_at,
            }

    def start(self, payload: dict[str, object], *, build_snapshot: SnapshotBuilder, run_pipeline: PipelineRunner) -> dict[str, object]:
        with self._lock:
            if self._state.status == "running":
                raise RenderJobAlreadyRunningError("render already in progress")
            self._state = RenderJobState(
                job_id=uuid4().hex,
                status="running",
                stage="Starting render",
                logs=[],
                error=None,
                started_at=_now_iso(),
                finished_at=None,
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
                run_pipeline(snapshot_path, progress=self._append_log)
        except Exception as exc:
            self._finish_failed(str(exc))
            return
        self._finish_succeeded()

    def _append_log(self, message: str) -> None:
        with self._lock:
            self._state.logs.append(message)
            if len(self._state.logs) > 500:
                self._state.logs = self._state.logs[-500:]
            self._state.stage = message

    def _finish_succeeded(self) -> None:
        with self._lock:
            self._state.status = "succeeded"
            self._state.finished_at = _now_iso()
            if not self._state.stage:
                self._state.stage = "Render completed"

    def _finish_failed(self, error: str) -> None:
        with self._lock:
            self._state.status = "failed"
            self._state.error = error
            self._state.finished_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
