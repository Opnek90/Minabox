"""Request and response schemas of the TTS Service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    """One phrase to be spoken."""

    text: str = Field(..., description="What should be said, as plain text")
    language: str | None = Field(
        default=None,
        description="de or en; anything unknown falls back to German",
    )


class SpeakResponse(BaseModel):
    """Where the finished clip is.

    ``path`` is deliberately a path and not audio: the clip is written into a
    volume the audio service has mounted at the same place, so handing over the
    name saves moving a WAV file through two HTTP hops for every card scan.
    """

    path: str
    language: str
    voice: str
    cached: bool
    bytes: int


class VoiceItem(BaseModel):
    """One language this box can speak."""

    language: str
    voice: str


class VoicesResponse(BaseModel):
    """The languages available right now."""

    voices: list[VoiceItem]
