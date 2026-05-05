"""Deterministic prompt-to-shell compiler for the graph explorer."""

from __future__ import annotations

import json
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse


DEFAULT_SHELL_SPEC = {
    "tone": "analyst",
    "density": "comfortable",
    "chrome": "floating",
    "graphPriority": "canvas",
    "drawerMode": "right",
}


def _has_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def compile_graph_shell_prompt(prompt: str):
    text = (prompt or "").strip().lower()
    spec = dict(DEFAULT_SHELL_SPEC)
    matched_rules = []

    if not text:
        return {"prompt": prompt or "", "spec": spec, "matched_rules": matched_rules}

    if _has_any(text, ["executive", "briefing", "presentation", "summary-first"]):
        spec["tone"] = "executive"
        spec["graphPriority"] = "balanced"
        matched_rules.append("executive tone")

    if _has_any(text, ["builder", "workspace", "developer", "tooling"]):
        spec["tone"] = "builder"
        spec["chrome"] = "docked"
        matched_rules.append("builder tone")

    if _has_any(text, ["compact", "dense", "more rows", "fit more"]):
        spec["density"] = "compact"
        matched_rules.append("compact density")

    if _has_any(text, ["comfortable", "spacious", "bigger panels"]):
        spec["density"] = "comfortable"
        matched_rules.append("comfortable density")

    if _has_any(text, ["floating controls", "floating chrome", "minimal chrome"]):
        spec["chrome"] = "floating"
        matched_rules.append("floating chrome")

    if _has_any(text, ["docked controls", "toolbar", "control rail"]):
        spec["chrome"] = "docked"
        matched_rules.append("docked chrome")

    if _has_any(text, ["graph first", "full canvas", "graph dominant", "canvas first", "graph-first"]):
        spec["graphPriority"] = "canvas"
        matched_rules.append("graph-first canvas")

    if _has_any(text, ["table first", "transactions first", "ledger first", "table-first"]):
        spec["graphPriority"] = "table"
        spec["drawerMode"] = "wide"
        matched_rules.append("table-first investigation")

    if _has_any(text, ["balanced", "split view"]):
        spec["graphPriority"] = "balanced"
        matched_rules.append("balanced split")

    if _has_any(text, ["wide drawer", "wide evidence drawer", "deeper drawer", "full evidence drawer"]):
        spec["drawerMode"] = "wide"
        matched_rules.append("wide drawer")

    if _has_any(text, ["right drawer", "standard drawer"]):
        spec["drawerMode"] = "right"
        matched_rules.append("right drawer")

    return {"prompt": prompt, "spec": spec, "matched_rules": matched_rules}


def shell_spec_summary(spec: dict):
    return " · ".join(
        [
            f"{spec.get('tone', 'analyst')} tone",
            f"{spec.get('density', 'comfortable')} density",
            f"{spec.get('chrome', 'floating')} chrome",
            f"{spec.get('graphPriority', 'canvas')} graph priority",
            f"{spec.get('drawerMode', 'right')} drawer",
        ]
    )


def with_query_params(url: str, params: dict):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, "")})
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_graph_shell_url(base_url: str, *, prompt: str, spec: dict, seed: str | None = None):
    return with_query_params(
        base_url,
        {
            "shell_prompt": prompt,
            "shell_spec": json.dumps(spec, separators=(",", ":")),
            "seed": seed or "",
        },
    )
