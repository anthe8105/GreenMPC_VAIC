"""Cached resources for the FastAPI command center adapter."""

from __future__ import annotations

from functools import lru_cache

from greenmpc.ui.state import ControlRoomResources, load_control_room_resources


@lru_cache(maxsize=1)
def get_resources() -> ControlRoomResources:
    """Load heavy immutable GreenMPC resources once per backend process."""

    return load_control_room_resources()
