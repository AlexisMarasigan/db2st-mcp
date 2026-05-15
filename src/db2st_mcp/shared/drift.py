"""Lightweight schema-drift detector for upstream payloads.

Records the top-level key-set fingerprint per logical endpoint. When a new
fingerprint shows up, emit a `schema.drift` warning (once per process per
fingerprint) so it surfaces in logs without spamming.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

_log = structlog.get_logger(__name__)
_seen: set[tuple[str, str]] = set()


def fingerprint(payload: Any) -> str:
    """Stable fingerprint of a payload's top-level key shape."""
    keys = _key_shape(payload)
    blob = json.dumps(keys, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _key_shape(value: Any, depth: int = 0, max_depth: int = 2) -> Any:
    if depth >= max_depth:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: _key_shape(v, depth + 1, max_depth) for k, v in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return ["empty"]
        return [_key_shape(value[0], depth + 1, max_depth)]
    return type(value).__name__


def check(endpoint: str, payload: Any) -> None:
    """Log if the payload shape for `endpoint` has not been seen before."""
    fp = fingerprint(payload)
    key = (endpoint, fp)
    if key in _seen:
        return
    if any(e == endpoint for e, _ in _seen):
        _log.warning("schema.drift", endpoint=endpoint, fingerprint=fp)
    else:
        _log.info("schema.first_seen", endpoint=endpoint, fingerprint=fp)
    _seen.add(key)
