import fnmatch
from glob import glob
from hashlib import sha256
import os
from pathlib import Path

from race_overlay.config import resolve_video_globs_from_config


def video_id(path: Path) -> str:
    canonical = path.resolve().as_posix().encode("utf-8")
    return sha256(canonical).hexdigest()[:24]


def _static_root(pattern: str) -> Path:
    path = Path(pattern)
    parts: list[str] = []
    for part in path.parts:
        if any(marker in part for marker in "*?["):
            break
        parts.append(part)
    if not parts:
        return Path.cwd().resolve()
    prefix = Path(*parts)
    if not any(marker in pattern for marker in "*?["):
        prefix = prefix.parent
    return prefix.resolve()


def discover_video_paths(patterns: list[str]) -> list[Path]:
    matches: dict[Path, Path] = {}
    for pattern in patterns:
        root = _static_root(pattern)
        candidates = {Path(match) for match in glob(pattern)}
        dirpart, name_pattern = os.path.split(pattern)
        if not any(marker in dirpart for marker in "*?["):
            base = Path(dirpart or ".")
            if base.exists():
                lowered = name_pattern.lower()
                candidates.update(
                    candidate
                    for candidate in base.rglob("*")
                    if candidate.is_file()
                    and fnmatch.fnmatch(candidate.name.lower(), lowered)
                )
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (FileNotFoundError, OSError, ValueError):
                continue
            if resolved.is_file():
                matches[resolved] = resolved
    return sorted(matches.values(), key=lambda path: path.as_posix())


def project_video_paths(config_path: Path, patterns: list[str]) -> list[Path]:
    return discover_video_paths(
        resolve_video_globs_from_config(config_path, patterns)
    )


def project_video_map(config_path: Path, patterns: list[str]) -> dict[str, Path]:
    return {video_id(path): path for path in project_video_paths(config_path, patterns)}
