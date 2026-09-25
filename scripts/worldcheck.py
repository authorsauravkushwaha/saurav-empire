#!/usr/bin/env python3
"""World geometry check — the 3D client draws exactly this, so this is what must be sound.

Validates the layout produced by `kernel.world_layout` (which comes from config/civilization.yaml)
and the agent positions the runtime writes, then emits an SVG map of the world so the arrangement
can be reviewed without a browser. Standard library only.

    python3 scripts/worldcheck.py                 # validate + write the map
    python3 scripts/worldcheck.py --no-processes  # ignore live agent positions
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kernel import paths, world_layout  # noqa: E402
from kernel.config import building_index, department_seeds  # noqa: E402

WARN = "\033[33m!\033[0m"
BAD = "\033[31m✗\033[0m"
OK = "\033[32m✓\033[0m"
DIM = "\033[2m"
RST = "\033[0m"


def footprint_radius(size: list[float]) -> float:
    """A conservative circle covering the building's base, used for overlap tests."""
    return math.hypot(size[0] / 2, size[2] / 2)


def check_layout() -> tuple[list[str], dict]:
    problems: list[str] = []
    data = world_layout.layout()
    cities = data["cities"]
    ground = float(data["ground_size"])
    half = ground / 2

    # 1. identity
    city_ids = [c["id"] for c in cities]
    if len(city_ids) != len(set(city_ids)):
        problems.append("duplicate city ids")
    building_ids: list[str] = []
    for city in cities:
        for b in city["buildings"]:
            building_ids.append(b["id"])
            if b.get("city") != city["id"]:
                problems.append(f"building {b['id']} claims city {b.get('city')} but sits in {city['id']}")
    if len(building_ids) != len(set(building_ids)):
        duplicated = {i for i in building_ids if building_ids.count(i) > 1}
        problems.append(f"duplicate building ids: {sorted(duplicated)}")

    # 2. cities inside the ground and not overlapping each other
    for city in cities:
        cx, _, cz = city["pos"]
        if abs(cx) + city["radius"] > half or abs(cz) + city["radius"] > half:
            problems.append(f"city {city['id']} ({cx:.0f},{cz:.0f}) r={city['radius']} reaches past the "
                            f"{ground:.0f}-unit ground")
    for i, a in enumerate(cities):
        for b in cities[i + 1:]:
            dist = math.dist((a["pos"][0], a["pos"][2]), (b["pos"][0], b["pos"][2]))
            if dist < a["radius"] + b["radius"]:
                problems.append(f"cities {a['id']} and {b['id']} overlap "
                                f"(distance {dist:.1f} < {a['radius'] + b['radius']:.1f})")

    # 3. buildings inside their city, and not intersecting each other
    for city in cities:
        cx, _, cz = city["pos"]
        placed: list[tuple[str, float, float, float]] = []
        for b in city["buildings"]:
            bx, _, bz = b["pos"]
            r = footprint_radius(b["size"])
            dist = math.dist((bx, bz), (cx, cz))
            if dist + r > city["radius"] + 1e-6:
                problems.append(f"{b['id']} pokes out of {city['id']} "
                                f"(centre {dist:.1f} + footprint {r:.1f} > radius {city['radius']:.1f})")
            placed.append((b["id"], bx, bz, r))
        for i, a in enumerate(placed):
            for other in placed[i + 1:]:
                gap = math.dist((a[1], a[2]), (other[1], other[2])) - (a[3] + other[3])
                if gap < -0.5:
                    problems.append(f"footprints overlap: {a[0]} and {other[0]} (gap {gap:.1f})")

    # 4. entry and workstation points must be usable (inside the plateau, near the building)
    for city in cities:
        for b in city["buildings"]:
            for label in ("entry", "workstation"):
                pt = b.get(label)
                if not pt:
                    problems.append(f"{b['id']} has no {label} point")
                    continue
                if math.dist((pt[0], pt[2]), (city["pos"][0], city["pos"][2])) > city["radius"]:
                    problems.append(f"{b['id']} {label} lies outside {city['id']}")

    # 5. every department seed points at a real building that exists in that city
    for seed in department_seeds():
        b = building_index().get(seed["building"])
        if not b:
            problems.append(f"department {seed['id']} targets unknown building {seed['building']}")
        elif b.get("city") != seed["city"]:
            problems.append(f"department {seed['id']} is assigned to {seed['city']} but its building "
                            f"sits in {b.get('city')}")

    summary = {
        "cities": len(cities),
        "buildings": len(building_ids),
        "ground_size": ground,
        "departments": len(department_seeds()),
        "data": data,
    }
    return problems, summary


def check_agents(summary: dict) -> tuple[list[str], list[dict]]:
    problems: list[str] = []
    db_path = paths.STATE_DIR / "empire.db"
    if not db_path.exists():
        return ["no database yet — run `empire.py up` once"], []
    known = building_index()
    half = summary["ground_size"] / 2
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    agents = [dict(r) for r in con.execute(
        "SELECT id, name, status, pos_x, pos_y, building, target_building FROM agents "
        "WHERE lifecycle != 'TERMINATED'")]
    seats_by_building: dict[str, set[tuple[float, float]]] = {}
    for a in agents:
        if a["building"] and a["building"] not in known:
            problems.append(f"{a['name']} stands in unknown building {a['building']}")
        if a["target_building"] and a["target_building"] not in known:
            problems.append(f"{a['name']} is heading to unknown building {a['target_building']}")
        x, z = float(a["pos_x"] or 0), float(a["pos_y"] or 0)
        if abs(x) > half or abs(z) > half:
            problems.append(f"{a['name']} is outside the ground at ({x:.0f},{z:.0f})")
        if a["building"]:
            seats_by_building.setdefault(a["building"], set()).add((round(x, 1), round(z, 1)))
    # Agents piled on one point render as a single capsule: the world would understate the workforce.
    for building, seats in seats_by_building.items():
        occupants = sum(1 for a in agents if a["building"] == building)
        if occupants > 1 and len(seats) < min(occupants, 4):
            problems.append(f"{occupants} agents share {len(seats)} position(s) at {building} — "
                            f"the 3D world would show fewer people than exist (run `empire.py repair`)")
    return problems, agents


def write_svg(summary: dict, agents: list[dict], out: Path) -> Path:
    """A top-down map of the world data — the same coordinates the 3D client renders."""
    data = summary["data"]
    ground = float(data["ground_size"])
    half = ground / 2
    size = 1100
    scale = size / ground
    status_colors = data["status_colors"]

    def sx(x: float) -> float:
        return (x + half) * scale

    def sz(z: float) -> float:
        return (z + half) * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        '<rect width="100%" height="100%" fill="#05060a"/>',
        f'<text x="20" y="34" fill="#e6e9f2" font-family="monospace" font-size="17">'
        f'SAURAV AI CIVILIZATION — world data map ({summary["cities"]} cities, '
        f'{summary["buildings"]} buildings, {len(agents)} agents)</text>',
        '<text x="20" y="56" fill="#8b93a7" font-family="monospace" font-size="12">'
        'top-down projection of the exact coordinates the 3D client renders · grey dots = agents'
        '</text>',
    ]
    for city in data["cities"]:
        cx, cz = sx(city["pos"][0]), sz(city["pos"][2])
        r = city["radius"] * scale
        parts.append(f'<circle cx="{cx:.1f}" cy="{cz:.1f}" r="{r:.1f}" fill="{city["theme"]}" '
                     f'fill-opacity="0.13" stroke="{city["theme"]}" stroke-opacity="0.85" stroke-width="1.6"/>')
        parts.append(f'<text x="{cx:.1f}" y="{cz - r - 8:.1f}" fill="{city["theme"]}" '
                     f'font-family="monospace" font-size="12" text-anchor="middle">{city["name"]}</text>')
        for b in city["buildings"]:
            bx, bz = sx(b["pos"][0]), sz(b["pos"][2])
            w, d = b["size"][0] * scale, b["size"][2] * scale
            parts.append(f'<rect x="{bx - w / 2:.1f}" y="{bz - d / 2:.1f}" width="{max(w, 3):.1f}" '
                         f'height="{max(d, 3):.1f}" fill="{b["theme"]}" fill-opacity="0.75" '
                         f'stroke="#0b0f19" stroke-width="0.6"/>')
    for a in agents:
        x, z = sx(float(a["pos_x"] or 0)), sz(float(a["pos_y"] or 0))
        color = status_colors.get(a["status"], "#8b93a7")
        parts.append(f'<circle cx="{x:.1f}" cy="{z:.1f}" r="2.6" fill="{color}" fill-opacity="0.95"/>')
    legend = " ".join(f"{s}({c})" for s, c in list(data["status_colors"].items()))
    parts.append(f'<text x="20" y="{size - 16}" fill="#5c6478" font-family="monospace" '
                 f'font-size="11">status colours: {legend}</text>')
    parts.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out



# ---------------------------------------------------------------------------
# A PNG is written too, so the map can be reviewed as an image (no SVG tooling required).
# ---------------------------------------------------------------------------
def _png(width: int, height: int, pixels: bytearray) -> bytes:
    import struct
    import zlib

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)                      # filter type 0
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def _hex(value: str) -> tuple[int, int, int]:
    value = (value or "#888888").lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


class Bitmap:
    def __init__(self, width: int, height: int, background: str = "#05060a") -> None:
        self.w, self.h = width, height
        colour = _hex(background)
        self.buf = bytearray(colour * (width * height))

    def _blend(self, x: int, y: int, colour: tuple[int, int, int], alpha: float) -> None:
        if not (0 <= x < self.w and 0 <= y < self.h) or alpha <= 0:
            return
        i = (y * self.w + x) * 3
        for c in range(3):
            self.buf[i + c] = int(self.buf[i + c] * (1 - alpha) + colour[c] * alpha)

    def disc(self, cx: float, cy: float, radius: float, colour: str, alpha: float) -> None:
        rgb = _hex(colour)
        for y in range(max(0, int(cy - radius)), min(self.h, int(cy + radius) + 1)):
            for x in range(max(0, int(cx - radius)), min(self.w, int(cx + radius) + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    self._blend(x, y, rgb, alpha)

    def ring(self, cx: float, cy: float, radius: float, colour: str, alpha: float, width: float = 1.4) -> None:
        rgb = _hex(colour)
        steps = max(64, int(radius * 6))
        import math as _m
        for i in range(steps):
            a = i / steps * _m.tau
            px, py = cx + _m.cos(a) * radius, cy + _m.sin(a) * radius
            for ox in range(-int(width), int(width) + 1):
                for oy in range(-int(width), int(width) + 1):
                    if ox * ox + oy * oy <= width * width:
                        self._blend(int(px) + ox, int(py) + oy, rgb, alpha)

    def rect(self, x: float, y: float, w: float, h: float, colour: str, alpha: float) -> None:
        rgb = _hex(colour)
        for py in range(max(0, int(y)), min(self.h, int(y + h) + 1)):
            for px in range(max(0, int(x)), min(self.w, int(x + w) + 1)):
                self._blend(px, py, rgb, alpha)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png(self.w, self.h, self.buf))
        return path


def write_png(summary: dict, agents: list[dict], out: Path, size: int = 900) -> Path:
    data = summary["data"]
    ground = float(data["ground_size"])
    half = ground / 2
    scale = size / ground
    status_colors = data["status_colors"]
    bmp = Bitmap(size, size)

    def sx(x: float) -> float:
        return (x + half) * scale

    for city in data["cities"]:
        cx, cz = sx(city["pos"][0]), sx(city["pos"][2])
        r = city["radius"] * scale
        bmp.disc(cx, cz, r, city["theme"], 0.10)
        bmp.ring(cx, cz, r, city["theme"], 0.85)
        for b in city["buildings"]:
            bx, bz = sx(b["pos"][0]), sx(b["pos"][2])
            w, d = b["size"][0] * scale, b["size"][2] * scale
            bmp.rect(bx - w / 2, bz - d / 2, max(w, 2), max(d, 2), b["theme"], 0.8)
    for a in agents:
        x, z = sx(float(a["pos_x"] or 0)), sx(float(a["pos_y"] or 0))
        bmp.disc(x, z, 2.6, status_colors.get(a["status"], "#8b93a7"), 0.95)
    return bmp.write(out)



def _look_at_axes(eye: list[float], target: list[float]) -> tuple[list[float], list[float], list[float]]:
    def sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    def norm(v):
        length = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / length for c in v]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    forward = norm(sub(target, eye))          # camera looks toward the target
    world_up = [0.0, 1.0, 0.0]
    right = norm(cross(forward, world_up))
    up = cross(right, forward)
    return right, up, forward


def _in_frustum(point: list[float], eye: list[float], right, up, forward, fov: float, aspect: float) -> bool:
    rel = [point[i] - eye[i] for i in range(3)]
    depth = sum(rel[i] * forward[i] for i in range(3))
    if depth <= 0:
        return False
    half_v = math.tan(math.radians(fov / 2)) * depth
    half_h = half_v * aspect
    x = sum(rel[i] * right[i] for i in range(3))
    y = sum(rel[i] * up[i] for i in range(3))
    return abs(x) <= half_h and abs(y) <= half_v


def check_camera(summary: dict) -> list[str]:
    """Project every city centre and building top through each preset and prove it is on screen."""
    data = summary["data"]
    camera = data.get("camera") or {}
    presets = camera.get("presets") or {}
    if not presets:
        return ["the layout carries no camera presets — the client would have to guess its framing"]
    fov = float(camera.get("fov", 45))
    aspect = 16 / 9

    problems: list[str] = []
    for name, preset in presets.items():
        eye = [float(v) for v in preset["pos"]]
        target = [float(v) for v in preset["target"]]
        right, up, forward = _look_at_axes(eye, target)
        scope = preset.get("scope", "centres")
        if scope == "all":
            for city in data["cities"]:
                centre = [city["pos"][0], 0.0, city["pos"][2]]
                # the city's edge, worst case at the screen's horizontal extreme
                for angle in range(0, 360, 45):
                    a = math.radians(angle)
                    edge = [centre[0] + math.cos(a) * city["radius"], 0.0,
                            centre[2] + math.sin(a) * city["radius"]]
                    if not _in_frustum(edge, eye, right, up, forward, fov, aspect):
                        problems.append(f"camera preset '{name}' crops {city['id']} "
                                        f"(edge at {angle}° is off screen)")
                        break
        for city in data["cities"]:
            if scope == "command" and city["id"] != "command":
                continue
            for b in city["buildings"]:
                top = [b["pos"][0], b["size"][1], b["pos"][2]]
                if not _in_frustum(top, eye, right, up, forward, fov, aspect):
                    problems.append(f"camera preset '{name}' (scope {scope}) crops the top of {b['id']}")
                    break
            else:
                continue
            break
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the world geometry and emit a map.")
    ap.add_argument("--no-processes", action="store_true", help="skip live agent position checks")
    ap.add_argument("--out", default=str(paths.ARTIFACT_DIR / "world-map.svg"))
    ap.add_argument("--png", default=str(paths.ARTIFACT_DIR / "world-map.png"))
    args = ap.parse_args()

    print("\n\033[1mWORLD GEOMETRY CHECK\033[0m\n")
    problems, summary = check_layout()
    print(f"  {OK} layout: {summary['cities']} cities, {summary['buildings']} buildings, "
          f"{summary['departments']} departments, {summary['ground_size']:.0f}-unit ground")
    camera_problems = check_camera(summary)
    problems += camera_problems
    cam = summary["data"].get("camera") or {}
    if camera_problems:
        print(f"  {BAD} camera framing problems: {len(camera_problems)}")
    else:
        print(f"  {OK} camera: every city and building fits the presets "
              f"(extent {cam.get('extent')}, needs {cam.get('distance_needed')} units of distance)")

    agents: list[dict] = []
    if not args.no_processes:
        agent_problems, agents = check_agents(summary)
        problems += agent_problems
        print(f"  {OK} live agents: {len(agents)} placed inside the world" if not agent_problems
              else f"  {BAD} live agent problems: {len(agent_problems)}")

    if problems:
        for p in problems[:40]:
            print(f"  {BAD} {p}")
        print(f"\n  {len(problems)} problem(s) — the 3D client is drawing from flawed data.\n")
    else:
        print(f"  {OK} no overlaps, no out-of-bounds buildings, no orphaned departments")

    out = write_svg(summary, agents, Path(args.out))
    print(f"  {OK} map written to {out.relative_to(ROOT)}")
    try:
        png = write_png(summary, agents, Path(args.png))
        print(f"  {OK} image written to {png.relative_to(ROOT)}")
    except Exception as exc:      # the SVG is the contract; the raster is a convenience
        print(f"  {WARN} PNG rendering skipped: {type(exc).__name__}")
    print(f"  {DIM}open it to see the cities, building footprints and every agent's position{RST}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
