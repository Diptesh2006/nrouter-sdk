"""nRouter Media: Audio format validation and video polling helpers."""

from __future__ import annotations

from nroutersdk._errors import nRouterRequestError

VALID_AUDIO_FORMATS: tuple[str, ...] = ("mp3", "opus", "aac", "flac", "wav", "pcm")


def validate_audio_format(format: str) -> None:
    """Validate that the given audio format is supported by nRouter speech."""
    if not isinstance(format, str):
        raise nRouterRequestError(f"audio format must be a string, got {type(format).__name__}")
    clean = format.strip().lower()
    if clean not in VALID_AUDIO_FORMATS:
        raise nRouterRequestError(
            f"Invalid audio format {format!r}; must be one of: {', '.join(VALID_AUDIO_FORMATS)}"
        )
