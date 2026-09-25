"""World layout math — the only place that converts config into world coordinates.

The frontend renders what this module says. The backend stores agent positions in the same
coordinate space, so "agent is at the Sales Floor" is a number, not an animation guess.
"""
from __future__ import annotations

import math

from .config import building_index, city_index, config

GROUND_DEFAULT = 900
BUILDING_GAP = 26

# The status palette lives with the layout because the world service and the client both need it;
# two copies would eventually drift and the 3D world would colour a status wrongly.
STATUS_COLORS: dict[str, str] = {
    "IDLE": "#8b93a7", "TRAVELING": "#60a5fa", "WORKING": "#22d3ee", "ANALYZING": "#a78bfa",
    "RESEARCHING": "#34d399", "CODING": "#fbbf24", "LEARNING": "#38bdf8", "WAITING": "#94a3b8",
    "NEGOTIATING": "#f472b6", "PUBLISHING": "#fb923c", "SELLING": "#4ade80", "ERROR": "#ef4444",
    "BLOCKED": "#f97316", "ESCALATED": "#dc2626", "COMPLETED": "#10b981",
}


def ground_size() -> float:
    return float(config().get("civilization.world.ground_size", GROUND_DEFAULT))


def city_center(city_id: str) -> list[float]:
    city = city_index().get(city_id)
    if not city:
        return [0.0, 0.0]
    pos = city.get("pos", [0, 0])
    return [float(pos[0]), float(pos[1])]


def building_world_pos(building_id: str) -> dict:
    """Absolute position + footprint of a building. y is height (Three.js convention)."""
    b = building_index().get(building_id)
    if not b:
        return {"id": building_id, "pos": [0, 0, 0], "size": [8, 8, 8], "city": None, "name": building_id}
    cx, cz = b.get("city_pos", [0, 0])
    bx, bz = b.get("pos", [0, 0])
    size = b.get("size", [10, 12, 10])
    x = float(cx) + float(bx)
    z = float(cz) + float(bz)
    return {
        "id": building_id,
        "name": b.get("name", building_id),
        "city": b.get("city"),
        "city_name": b.get("city_name"),
        "theme": b.get("theme"),
        "shape": b.get("shape", "block"),
        "pos": [x, 0.0, z],
        "size": [float(size[0]), float(size[1]), float(size[2])],
        "slots": int(b.get("slots", 8)),
        "purpose": b.get("purpose", ""),
        "entry": [x, 0.0, z + float(size[2]) / 2 + 4.0],
        "workstation": [x, 0.0, z - float(size[2]) / 2 - 2.5],
    }


def layout() -> dict:
    """Full world layout consumed by world-service → React Three Fiber."""
    cities = []
    for city in config().get("civilization.cities", []) or []:
        pos = city.get("pos", [0, 0])
        buildings = [building_world_pos(b["id"]) for b in city.get("buildings", []) or []]
        cities.append({
            "id": city["id"],
            "name": city["name"],
            "tagline": city.get("tagline", ""),
            "theme": city.get("theme", "#888888"),
            "pos": [float(pos[0]), 0.0, float(pos[1])],
            "radius": float(city.get("radius", 60)),
            "buildings": buildings,
        })
    return {"ground_size": ground_size(), "cities": cities,
            "status_colors": STATUS_COLORS,
            "camera": camera_presets(),
            "style": config().get("civilization.world.ambient", "dusk")}


SEATS_PER_RING = 12
SEAT_RING_GAP = 2.3


def seat_position(building_id: str, slot: int) -> list[float]:
    """Where the `slot`-th occupant of a building stands.

    Seats ring the building just outside its walls and are clamped inside the city disc, so a
    building with 25 occupants renders as a crowd around it instead of 25 capsules in one point.
    Deterministic: the same slot always yields the same seat.
    """
    b = building_world_pos(building_id)
    bx, _, bz = b["pos"]
    w, _, d = b["size"]
    base = max(w, d) / 2 + 2.4
    ring = max(0, int(slot)) // SEATS_PER_RING
    idx = max(0, int(slot)) % SEATS_PER_RING
    angle = (idx / SEATS_PER_RING) * math.tau + ring * 0.37
    r = base + ring * SEAT_RING_GAP
    x, z = bx + math.cos(angle) * r, bz + math.sin(angle) * r

    city = city_index().get(b.get("city") or "")
    if city:
        cx, cz = float(city.get("pos", [0, 0])[0]), float(city.get("pos", [0, 0])[1])
        limit = float(city.get("radius", 60)) - 2.0
        dx, dz = x - cx, z - cz
        dist = math.hypot(dx, dz)
        if dist > limit and dist > 0:
            x, z = cx + dx / dist * limit, cz + dz / dist * limit
    return [x, 0.0, z]


def room_for(building_id: str) -> int:
    """How many seats a building can offer inside its city disc, at least one ring."""
    b = building_world_pos(building_id)
    city = city_index().get(b.get("city") or "")
    limit = float(city.get("radius", 60)) if city else 60.0
    w, _, d = b["size"]
    base = max(w, d) / 2 + 2.4
    rings = max(1, int((limit - base - 2) / SEAT_RING_GAP) + 1)
    return rings * SEATS_PER_RING


# ---------------------------------------------------------------------------
# Camera framing
# ---------------------------------------------------------------------------
# The presets live here, not in the client, because they must frame a world whose size comes from
# config. A hard-coded camera distance silently crops the civilization as the world grows.
CAMERA_FOV_DEGREES = 45.0


def world_extent() -> float:
    """Distance from the origin to the furthest edge of any city."""
    extent = 60.0
    for city in config().get("civilization.cities", []) or []:
        pos = city.get("pos", [0, 0])
        extent = max(extent, math.hypot(float(pos[0]), float(pos[1])) + float(city.get("radius", 60)))
    return extent


def camera_presets() -> dict:
    """Preset viewpoints that actually contain the whole world, as the client's fov sees it."""
    extent = world_extent()
    radians = math.radians(CAMERA_FOV_DEGREES / 2)
    # distance needed for a sphere of `extent` to fit the vertical fov, with a 12% margin
    fit = extent / math.sin(radians) * 1.12
    tilt = math.radians(52)          # angle above the horizon
    overview = [0.0, round(fit * math.sin(tilt), 1), round(fit * math.cos(tilt), 1)]
    ring_tilt = math.radians(40)
    ring = [round(fit * math.cos(ring_tilt) * 0.72, 1),
            round(fit * math.sin(ring_tilt), 1),
            round(fit * math.cos(ring_tilt) * 0.72, 1)]
    command = [0.0, round(extent * 1.15, 1), round(extent * 1.05, 1)]
    return {
        "fov": CAMERA_FOV_DEGREES,
        "extent": round(extent, 1),
        "distance_needed": round(fit, 1),
        "presets": {
            "overview": {"pos": overview, "target": [0.0, 0.0, 0.0], "scope": "all",
                         "note": "the whole civilization, edge to edge"},
            "command": {"pos": command, "target": [0.0, 0.0, 0.0], "scope": "command",
                        "note": "close enough to read the Command City"},
            "ring": {"pos": ring, "target": [0.0, 0.0, 0.0], "scope": "centres",
                     "note": "oblique view across the city ring"},
        },
    }


def deck_position(building_id: str, slot: int, slots: int) -> list[float]:
    """Backwards-compatible alias for the seat layout."""
    return seat_position(building_id, slot)


def distance(a: list[float], b: list[float]) -> float:
    return math.dist(a[:2], b[:2])


def step_towards(current: list[float], target: list[float], speed: float) -> list[float]:
    """Move up to `speed` units toward target. Returns the new position."""
    x, z = current[0], current[1] if len(current) > 1 else 0.0
    tx, tz = target[0], target[1]
    dx, dz = tx - x, tz - z
    dist = math.hypot(dx, dz)
    if dist <= speed or dist == 0:
        return [tx, tz]
    return [x + dx / dist * speed, z + dz / dist * speed]
