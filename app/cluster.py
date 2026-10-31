"""Deterministic pre-clustering + rule-based labels.

Groups a flat list of file metadata into a small number of "bosses"
so that one player decision can resolve hundreds of files.
This layer works with zero AI; Gemini only improves names/targets.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

from .models import FileMeta, Group

DUP_RE = re.compile(r"(\(\d+\)|[ _-]copy\b|[ _-]copy[ _-]?\d*)", re.IGNORECASE)
SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9 _\-]")

EXT_FAMILIES: dict[str, set[str]] = {
    "installers": {"exe", "msi", "dmg", "pkg", "deb", "rpm", "apk", "appimage"},
    "archives": {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2"},
    "images": {"jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "svg", "tiff"},
    "videos": {"mp4", "mov", "mkv", "avi", "webm"},
    "audio": {"mp3", "wav", "m4a", "flac", "aac", "ogg"},
    "pdfs": {"pdf"},
    "documents": {"doc", "docx", "odt", "rtf", "txt", "md", "pages"},
    "spreadsheets": {"xls", "xlsx", "csv", "ods", "numbers"},
    "slides": {"ppt", "pptx", "key", "odp"},
    "code": {"py", "js", "ts", "java", "cpp", "c", "h", "ipynb", "json", "html", "css", "sh", "sql"},
}

# category -> (boss name, target folder, action, confidence, reason)
RULES: dict[str, tuple[str, str, str, float, str]] = {
    "duplicates": ("The Clone Army", "Duplicates", "archive", 0.9, "Copies like (1) and _copy are almost always junk"),
    "installers": ("Installer Hoard", "Installers", "archive", 0.9, "Setup files are useless once installed"),
    "screenshots": ("Screenshot Swarm", "Pictures/Screenshots", "move", 0.9, "Screenshots grouped by month"),
    "invoices": ("Receipt Kraken", "Finance/Invoices", "move", 0.85, "Bills and receipts belong together"),
    "resumes": ("Resume Hydra", "Career/Resume", "move", 0.8, "Every resume_final_v7 in one place"),
    "archives": ("Zip Golem", "Archives", "move", 0.7, "Compressed files may still be needed"),
    "images": ("Photo Phantom", "Pictures", "move", 0.8, "Photos and images"),
    "videos": ("Reel Wraith", "Videos", "move", 0.85, "Video files"),
    "audio": ("Sound Banshee", "Music", "move", 0.85, "Audio files"),
    "pdfs": ("PDF Leviathan", "Documents/PDFs", "move", 0.6, "Mixed PDFs, worth a human look"),
    "documents": ("Doc Goblin", "Documents", "move", 0.65, "Mixed documents"),
    "spreadsheets": ("Sheet Serpent", "Documents/Spreadsheets", "move", 0.75, "Spreadsheets and CSVs"),
    "slides": ("Slide Specter", "Documents/Presentations", "move", 0.8, "Presentation decks"),
    "code": ("Code Gremlin", "Code", "move", 0.6, "Loose code files, check before moving"),
    "misc": ("The Unknown", "Misc", "move", 0.4, "Hard to classify, you decide"),
}

MIN_GROUP = 3


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def category_of(name: str) -> str:
    low = name.lower()
    ext = ext_of(name)
    if DUP_RE.search(low.rsplit(".", 1)[0]):
        return "duplicates"
    if ext in EXT_FAMILIES["installers"]:
        return "installers"
    if "screenshot" in low or "screen shot" in low or low.startswith("screen recording"):
        return "screenshots"
    if re.search(r"invoice|receipt|bill|payment|statement|txn", low):
        return "invoices"
    if re.search(r"resume|\bcv\b|cv[_-]|cover[ _-]?letter", low):
        return "resumes"
    for fam, exts in EXT_FAMILIES.items():
        if ext in exts:
            return fam
    return "misc"


def year_month(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def sanitize_folder(path: str) -> str:
    """Relative, max 3 segments, no traversal, safe characters only."""
    parts = []
    for seg in re.split(r"[\\/]+", path or ""):
        seg = SAFE_SEGMENT_RE.sub("", seg).strip()
        if not seg or seg in {".", ".."} or seg.startswith("."):
            continue
        parts.append(seg[:40])
    return "/".join(parts[:3]) or "Misc"


def pre_cluster(files: list[FileMeta]) -> list[Group]:
    buckets: dict[str, list[FileMeta]] = defaultdict(list)
    for f in files:
        buckets[category_of(f.name)].append(f)

    # fold tiny buckets into misc so the player is not spammed with 1-file bosses
    for cat in list(buckets):
        if cat != "misc" and len(buckets[cat]) < MIN_GROUP:
            buckets["misc"].extend(buckets.pop(cat))

    groups: list[Group] = []
    for i, (cat, members) in enumerate(sorted(buckets.items(), key=lambda kv: -len(kv[1]))):
        boss, target, action, conf, reason = RULES.get(cat, RULES["misc"])
        groups.append(
            Group(
                group_id=f"g{i}",
                category=cat,
                boss_name=boss,
                target_folder=target,
                action=action,
                confidence=conf,
                reason=reason,
                files=[m.name for m in members],
                samples=[m.name for m in members[:6]],
                date_range=_date_range(members),
            )
        )
    return groups


def split_group(parent_target: str, files: list[FileMeta]) -> list[Group]:
    """Split one boss into smaller ones by month (or by first name token)."""
    by_month: dict[str, list[FileMeta]] = defaultdict(list)
    for f in files:
        by_month[year_month(f.mtime)].append(f)
    if len(by_month) < 2:
        by_month = defaultdict(list)
        for f in files:
            token = re.split(r"[ _\-.()]+", f.name.lower())[0] or "other"
            by_month[token[:20].title()].append(f)
    parent = sanitize_folder(parent_target)
    out = []
    for i, (key, members) in enumerate(sorted(by_month.items())):
        out.append(
            Group(
                group_id=f"s{i}",
                category="split",
                boss_name=f"Minion {key}",
                target_folder=sanitize_folder(f"{parent}/{key}"),
                action="move",
                confidence=0.7,
                reason=f"Split from {parent} by {key}",
                files=[m.name for m in members],
                samples=[m.name for m in members[:6]],
                date_range=_date_range(members),
            )
        )
    return out


def _date_range(members: list[FileMeta]) -> str:
    months = sorted({year_month(m.mtime) for m in members})
    return months[0] if len(months) == 1 else f"{months[0]} to {months[-1]}"
