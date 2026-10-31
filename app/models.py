from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_FILES = 3000


class FileMeta(BaseModel):
    """Metadata only. File contents never leave the user's computer."""

    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    mtime: float = Field(ge=0, description="lastModified in ms")


class ClusterRequest(BaseModel):
    files: list[FileMeta] = Field(max_length=MAX_FILES)


class SplitRequest(BaseModel):
    parent_target: str = Field(max_length=200)
    files: list[FileMeta] = Field(min_length=1, max_length=MAX_FILES)


class Group(BaseModel):
    group_id: str
    category: str
    boss_name: str
    target_folder: str
    action: Literal["move", "archive"]
    confidence: float = Field(ge=0, le=1)
    reason: str
    files: list[str]
    samples: list[str]
    date_range: str = ""


class ClusterResponse(BaseModel):
    groups: list[Group]
    ai: bool
    total_files: int
