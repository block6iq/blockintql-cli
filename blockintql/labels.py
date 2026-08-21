"""
Local label sources for OSS screening.

The deterministic core is reasoning-only until labels are supplied. This module
loads:

1. Bundled public OFAC crypto address snapshot (package data)
2. Optional user file: ~/.blockintql/ofac_sanctioned_crypto_addresses.txt
3. Optional env: BLOCKINTQL_SANCTIONS_FILE
4. Optional JSON own-labels: --labels path or ~/.blockintql/labels.json

Sanctions hits are hard BLOCK inputs for Sentinel / adjudicate().
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


CONFIG_DIR = Path(os.path.expanduser("~/.blockintql"))
DEFAULT_USER_SANCTIONS = CONFIG_DIR / "ofac_sanctioned_crypto_addresses.txt"
DEFAULT_USER_LABELS = CONFIG_DIR / "labels.json"
BUNDLED_SANCTIONS = Path(__file__).resolve().parent / "data" / "ofac_sanctioned_crypto_addresses.txt"

_SANCTIONS_LABEL = {
    "entity_name": "OFAC SDN",
    "entity_category": "sanctions",
    "risk_score": 100.0,
    "sanctions_hit": True,
    "risk_indicators": ["OFAC", "sanctions", "SDN"],
}


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


_ETH_ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")


def _normalize_address(value: str) -> str:
    text = str(value or "").strip()
    match = _ETH_ADDR_RE.search(text)
    if match:
        return match.group(0).lower()
    return text.lower()


def _iter_address_lines(path: Path) -> Iterable[str]:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Allow "0xabc..." or "0xabc... # comment"
        token = line.split()[0].strip().lower()
        if token.startswith("0x") or token.isalnum():
            yield token


@lru_cache(maxsize=4)
def load_sanctions_addresses(extra_path: str | None = None) -> frozenset[str]:
    """Load sanctioned addresses from env, user file, and bundled snapshot."""
    paths: list[Path] = []
    env_path = str(os.environ.get("BLOCKINTQL_SANCTIONS_FILE") or "").strip()
    if env_path:
        paths.append(Path(os.path.expanduser(env_path)))
    if extra_path:
        paths.append(Path(os.path.expanduser(extra_path)))
    paths.append(DEFAULT_USER_SANCTIONS)
    paths.append(BUNDLED_SANCTIONS)

    found: Set[str] = set()
    for path in paths:
        for addr in _iter_address_lines(path):
            found.add(addr)
    return frozenset(found)


def clear_sanctions_cache() -> None:
    load_sanctions_addresses.cache_clear()


def normalize_own_labels(own_labels: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not own_labels:
        return {}
    out: Dict[str, Any] = {}
    for key, value in own_labels.items():
        addr = _normalize_address(key)
        if not addr:
            continue
        if isinstance(value, dict):
            out[addr] = value
        else:
            out[addr] = {"entity_category": str(value), "risk_indicators": [str(value)]}
    return out


def load_json_labels(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(os.path.expanduser(str(path)))
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return normalize_own_labels(data)


def sanctions_label_for(address: str) -> Optional[Dict[str, Any]]:
    addr = _normalize_address(address)
    if not addr:
        return None
    if addr in load_sanctions_addresses():
        return dict(_SANCTIONS_LABEL)
    return None


def resolve_own_labels(
    address: str | None = None,
    *,
    labels_path: str | None = None,
    use_bundled_sanctions: bool | None = None,
    extra_labels: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build own_labels for adjudicate().

    Priority (later wins):
      bundled/user OFAC set → ~/.blockintql/labels.json → labels_path → extra_labels
    """
    if use_bundled_sanctions is None:
        use_bundled_sanctions = _env_flag("BLOCKINTQL_BUNDLED_SANCTIONS", True)

    labels: Dict[str, Any] = {}

    if use_bundled_sanctions:
        sanctions = load_sanctions_addresses()
        if address:
            addr = _normalize_address(address)
            if addr in sanctions:
                labels[addr] = dict(_SANCTIONS_LABEL)
        else:
            # Full map only when caller needs bulk; usually address-scoped.
            for addr in sanctions:
                labels[addr] = dict(_SANCTIONS_LABEL)

    # User JSON labels (optional)
    labels.update(load_json_labels(DEFAULT_USER_LABELS))
    if labels_path:
        labels.update(load_json_labels(labels_path))
    if extra_labels:
        labels.update(normalize_own_labels(extra_labels))

    if address:
        addr = _normalize_address(address)
        return {addr: labels[addr]} if addr in labels else {}
    return labels


def label_sources_summary() -> Dict[str, Any]:
    sanctions = load_sanctions_addresses()
    return {
        "bundled_sanctions_file": str(BUNDLED_SANCTIONS) if BUNDLED_SANCTIONS.is_file() else None,
        "user_sanctions_file": str(DEFAULT_USER_SANCTIONS) if DEFAULT_USER_SANCTIONS.is_file() else None,
        "env_sanctions_file": os.environ.get("BLOCKINTQL_SANCTIONS_FILE") or None,
        "user_labels_file": str(DEFAULT_USER_LABELS) if DEFAULT_USER_LABELS.is_file() else None,
        "bundled_sanctions_enabled": _env_flag("BLOCKINTQL_BUNDLED_SANCTIONS", True),
        "sanctions_address_count": len(sanctions),
    }
