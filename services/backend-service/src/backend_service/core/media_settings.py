"""Media import (URL download) settings read from general_settings.json.

Which hosts a track can be imported from is a technical guard against
arbitrary fetch targets, not a legal clearance of the content hosted there
(see the lawful-use notice in the WebUI and media-downloader-service's
README.md). Like everything in general_settings.json, the list is read fresh
on each access, so a change in the WebUI takes effect without a restart.
"""

from __future__ import annotations

from backend_service.core.general_settings import read_general_settings

# YouTube is deliberately not on this list by default: unlike SoundCloud and
# Bandcamp, which both offer downloading as a feature the rights holder
# explicitly opts into, YouTube (and other pure streaming platforms) have no
# such mechanism, and importing from them carries meaningfully higher legal
# risk. A user who has satisfied themselves that they hold the necessary
# rights for a specific source can still add it in the WebUI.
DEFAULT_ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "soundcloud.com",
    "www.soundcloud.com",
    "bandcamp.com",
})

_MAX_DOMAINS = 20


def clamp_allowed_domains(value: object) -> list[str]:
    """Normalize a raw settings value into a deduplicated hostname list.

    Unknown/malformed input falls back to the default list rather than an
    empty one - an empty allow-list would silently accept no domain at all,
    while callers reading this expect it to be non-empty for the URL-import
    feature to work.
    """
    if not isinstance(value, list):
        return sorted(DEFAULT_ALLOWED_DOMAINS)
    domains: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        host = item.strip().lower()
        if host and host not in domains:
            domains.append(host)
        if len(domains) >= _MAX_DOMAINS:
            break
    return domains or sorted(DEFAULT_ALLOWED_DOMAINS)


def read_allowed_domains() -> frozenset[str]:
    """Hostnames a media URL is currently allowed to come from."""
    raw = read_general_settings().get("media_import_allowed_domains")
    if raw is None:
        return DEFAULT_ALLOWED_DOMAINS
    return frozenset(clamp_allowed_domains(raw))


__all__ = [
    "DEFAULT_ALLOWED_DOMAINS",
    "clamp_allowed_domains",
    "read_allowed_domains",
]
