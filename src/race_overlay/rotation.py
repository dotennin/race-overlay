from dataclasses import dataclass

from race_overlay.models import VideoClip


VALID_ROTATIONS = (0, 90, 180, 270)


def validate_rotation_degrees(value: int) -> int:
    if isinstance(value, bool) or value not in VALID_ROTATIONS:
        raise ValueError("rotation_degrees must be 0, 90, 180, or 270")
    return value


@dataclass(slots=True, frozen=True)
class RotationSpec:
    source_degrees: int
    user_degrees: int
    effective_degrees: int
    encoded_width: int
    encoded_height: int
    display_width: int
    display_height: int

    @classmethod
    def from_clip(cls, clip: VideoClip, user_degrees: int = 0) -> "RotationSpec":
        source = validate_rotation_degrees(clip.source_rotation_degrees)
        user = validate_rotation_degrees(user_degrees)
        effective = (source + user) % 360
        if effective in (90, 270):
            display_width, display_height = clip.height, clip.width
        else:
            display_width, display_height = clip.width, clip.height
        return cls(
            source_degrees=source,
            user_degrees=user,
            effective_degrees=effective,
            encoded_width=clip.width,
            encoded_height=clip.height,
            display_width=display_width,
            display_height=display_height,
        )
