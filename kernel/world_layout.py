"""World layout math — the only place that converts config into world coordinates.

The frontend renders what this module says. The backend stores agent positions in the same
coordinate space, so "agent is at the Sales Floor" is a number, not an animation guess.
"""
from __future__ import annotations

import math

from .config import building_index, city_index, config

GROUND_DEFAULT = 900
BUILDING_GAP = 26


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
            "style": config().get("civilization.world.ambient", "dusk")}


def deck_position(building_id: str, slot: int, slots: int) -> list[float]:
    """Where an agent stands inside a building (deterministic seating, no randomness)."""
    b = building_world_pos(building_id)
    wx, _, wz = b["workstation"]
    ring = 1 + (slot // 8)
    idx = slot % 8
    angle = (idx / 8) * math.tau
    r = 1.6 * ring
    return [wx + math.cos(angle) * r, 0.0, wz + math.sin(angle) * r]


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
