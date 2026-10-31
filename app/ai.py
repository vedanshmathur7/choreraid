"""Gemini labelling layer. Optional: the app works in rule mode without a key."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from functools import lru_cache

from .cluster import sanitize_folder
from .models import Group

log = logging.getLogger("choreraid.ai")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_SAMPLES_PER_GROUP = 12  # keeps the prompt small and fast regardless of folder size
TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT", "12"))

SYSTEM_PROMPT = """You are the planner inside ChoreRaid, a game that cleans a messy folder.
You receive groups of files (metadata only: names, counts, date ranges).
For EACH group return an object:
- group_id: copy exactly
- boss_name: a fun video-game boss name, max 3 words, inspired by the files
- target_folder: relative path, Title Case, 1-3 levels, no dots, e.g. "Finance/Invoices/2026"
- action: "move" or "archive" (archive = probably junk, e.g. installers, duplicates)
- confidence: 0..1. Use < 0.75 when filenames are mixed or ambiguous, so a human decides.
- reason: max 10 words, plain English, why this plan
Rules: never suggest deleting. Screenshots -> Pictures/Screenshots. Invoices/receipts -> Finance.
Resumes/CVs -> Career. Old installers and "(1)"/"copy" duplicates -> archive.
Return only JSON."""

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "group_id": {"type": "STRING"},
            "boss_name": {"type": "STRING"},
            "target_folder": {"type": "STRING"},
            "action": {"type": "STRING", "enum": ["move", "archive"]},
            "confidence": {"type": "NUMBER"},
            "reason": {"type": "STRING"},
        },
        "required": ["group_id", "boss_name", "target_folder", "action", "confidence", "reason"],
    },
}


def ai_enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


@lru_cache(maxsize=1)
def _client():
    """One shared Gemini client per process (reuses HTTP connections)."""
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _call_gemini(payload: list[dict]) -> list[dict]:
    from google.genai import types

    resp = _client().models.generate_content(
        model=MODEL,
        contents=json.dumps(payload),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.4,
        ),
    )
    return json.loads(resp.text)


def merge_labels(groups: list[Group], labels: list[dict]) -> list[Group]:
    """Apply AI labels on top of rule labels, validating every field."""
    by_id = {str(lbl.get("group_id")): lbl for lbl in labels if isinstance(lbl, dict)}
    out = []
    for g in groups:
        lbl = by_id.get(g.group_id)
        if not lbl:
            out.append(g)
            continue
        try:
            conf = float(lbl.get("confidence", g.confidence))
        except (TypeError, ValueError):
            conf = g.confidence
        action = lbl.get("action") if lbl.get("action") in ("move", "archive") else g.action
        out.append(
            g.model_copy(
                update={
                    "boss_name": str(lbl.get("boss_name") or g.boss_name)[:40],
                    "target_folder": sanitize_folder(str(lbl.get("target_folder") or g.target_folder)),
                    "action": action,
                    "confidence": max(0.0, min(1.0, conf)),
                    "reason": str(lbl.get("reason") or g.reason)[:90],
                }
            )
        )
    return out


async def label_groups(groups: list[Group]) -> tuple[list[Group], bool]:
    """Returns (groups, ai_used). Falls back to rule labels on any failure."""
    if not ai_enabled() or not groups:
        return groups, False
    payload = [
        {
            "group_id": g.group_id,
            "rule_category": g.category,
            "count": len(g.files),
            "date_range": g.date_range,
            "sample_names": g.files[:MAX_SAMPLES_PER_GROUP],
        }
        for g in groups
    ]
    try:
        labels = await asyncio.wait_for(asyncio.to_thread(_call_gemini, payload), TIMEOUT_S)
        return merge_labels(groups, labels), True
    except Exception as exc:  # network, quota, bad JSON: never break the game
        log.warning("Gemini failed, using rule labels: %s", exc)
        return groups, False
