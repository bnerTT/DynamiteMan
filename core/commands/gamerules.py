from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
import random

from core.entities.bomb import Bomb
from core.entities.player import Player
from core.vos.action import Action
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.powerup import PowerUpType
from core.vos.walls import Wall

DEFAULT_BOMB_FUSE: int = 8
DEFAULT_BLAST_RADIUS: int = 2
FLAME_DURATION_TICKS: int = 2
DEFAULT_MAX_TICKS: int = 240
SUDDEN_DEATH_START_TICK: int = 140
POWERUP_DROP_CHANCE: float = 0.38

DIRECTION_DELTAS: dict[Action, tuple[int, int, Direction]] = {
    Action.UP: (0, -1, Direction.UP),
    Action.DOWN: (0, 1, Direction.DOWN),
    Action.LEFT: (-1, 0, Direction.LEFT),
    Action.RIGHT: (1, 0, Direction.RIGHT),
}

ALL_POWERUPS: tuple[PowerUpType, ...] = (
    PowerUpType.BOMB_UP,
    PowerUpType.FIRE_UP,
    PowerUpType.SPEED_UP,
)


@dataclass
class PlayerStepEvents:
    player_id: int
    moved: bool = False
    bumped_wall: bool = False
    placed_bomb: bool = False
    invalid_bomb: bool = False
    picked_powerup: bool = False
    boxes_destroyed: int = 0
    kills: int = 0
    died: bool = False
    suicided: bool = False
    won_match: bool = False
    survived_tick: bool = False


# Cached spiral coordinates by (width, height)
_spiral_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}

# Per-tick caches so all 4 AI agents share board analysis in O(1)
_danger_cache_key: tuple[int, int, int] | None = None
_danger_cache_val: dict[tuple[int, int], int] = {}
_box_adj_cache_key: tuple[int, int] | None = None
_box_adj_cache_val: set[tuple[int, int]] = set()
_spacetime_cache_key: tuple[int, int, int] | None = None
_spacetime_cache_val: SpaceTimeHazardModel | None = None


def get_spiral_coords(width: int = 9, height: int = 9) -> list[tuple[int, int]]:
    """
    Returns clockwise inward spiral coordinates for the outer 2 rings
    (leaving the inner 5x5 deathmatch cage 2 <= x <= width-3, 2 <= y <= height-3 intact).
    """
    key = (width, height)
    if key in _spiral_cache:
        return _spiral_cache[key]

    coords: list[tuple[int, int]] = []
    left, right = 0, width - 1
    top, bottom = 0, height - 1

    # Close the outer 2 layers (layer 0 and layer 1), leaving the 5x5 inner arena (2..6)
    for _layer in range(2):
        if left > right or top > bottom:
            break
        for x in range(left, right + 1):
            if not (x % 2 == 1 and top % 2 == 1):
                coords.append((x, top))
        top += 1

        for y in range(top, bottom + 1):
            if not (right % 2 == 1 and y % 2 == 1):
                coords.append((right, y))
        right -= 1

        if top <= bottom:
            for x in range(right, left - 1, -1):
                if not (x % 2 == 1 and bottom % 2 == 1):
                    coords.append((x, bottom))
            bottom -= 1

        if left <= right:
            for y in range(bottom, top - 1, -1):
                if not (left % 2 == 1 and y % 2 == 1):
                    coords.append((left, y))
            left += 1

    _spiral_cache[key] = coords
    return coords


def get_upcoming_sudden_death_tiles(
    state: Gamestate, lookahead: int = 5
) -> list[tuple[int, int, int]]:
    """
    Returns a list of (x, y, ticks_until_collapse) for the next `lookahead`
    Sudden Death tiles that will turn into CONCRETE.
    """
    spiral = get_spiral_coords(state.width, state.height)
    if state.sudden_death_index >= len(spiral):
        return []

    ticks_until_start = max(1, SUDDEN_DEATH_START_TICK - state.current_tick)
    if ticks_until_start > lookahead:
        return []

    upcoming: list[tuple[int, int, int]] = []
    for offset in range(lookahead):
        t_collapse = ticks_until_start + offset
        if t_collapse > lookahead:
            break
        idx = state.sudden_death_index + offset
        if idx >= len(spiral):
            break
        sx, sy = spiral[idx]
        upcoming.append((sx, sy, t_collapse))

    return upcoming


def reset_tick_cache() -> None:
    global _danger_cache_key, _danger_cache_val, _box_adj_cache_key, _box_adj_cache_val
    global _spacetime_cache_key, _spacetime_cache_val
    _danger_cache_key = None
    _danger_cache_val = {}
    _box_adj_cache_key = None
    _box_adj_cache_val = set()
    _spacetime_cache_key = None
    _spacetime_cache_val = None


def clone(state: Gamestate) -> Gamestate:
    new_gs = Gamestate()
    new_gs.current_tick = state.current_tick
    new_gs.width = state.width
    new_gs.height = state.height
    new_gs.grid_walls = [row[:] for row in state.grid_walls]
    new_gs.flames_grid = [row[:] for row in state.flames_grid]
    new_gs.flame_owners = [row[:] for row in state.flame_owners]
    new_gs.bombs = [b.clone() for b in state.bombs]
    new_gs.players = [p.clone() for p in state.players]
    new_gs.powerups = dict(state.powerups)
    new_gs.sudden_death_index = state.sudden_death_index
    new_gs.next_bomb_id = state.next_bomb_id
    new_gs.max_ticks = state.max_ticks
    new_gs.is_over = state.is_over
    new_gs.winner_id = state.winner_id
    return new_gs


def is_in_bounds(state: Gamestate, x: int, y: int) -> bool:
    return 0 <= x < state.width and 0 <= y < state.height


def has_bomb_at(state: Gamestate, x: int, y: int) -> bool:
    for b in state.bombs:
        if b.pos.x == x and b.pos.y == y:
            return True
    return False


def is_walkable(state: Gamestate, x: int, y: int) -> bool:
    if not is_in_bounds(state, x, y):
        return False
    if state.grid_walls[y][x] != Wall.EMPTY:
        return False
    if has_bomb_at(state, x, y):
        return False
    return True


def is_flame(state: Gamestate, x: int, y: int) -> bool:
    if not is_in_bounds(state, x, y):
        return False
    return state.flames_grid[y][x] >= 0


def get_blast_rays(
    state: Gamestate, origin: Position, blast_radius: int
) -> tuple[list[Position], list[Position]]:
    """
    Computes the tiles affected by a bomb explosion at `origin`.
    Returns (flame_positions, hit_box_positions).
    """
    flames: list[Position] = [origin]
    boxes: list[Position] = []

    ox, oy = origin.x, origin.y
    w, h = state.width, state.height
    walls = state.grid_walls

    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        for step in range(1, blast_radius + 1):
            nx = ox + dx * step
            ny = oy + dy * step
            if not (0 <= nx < w and 0 <= ny < h):
                break
            wall = walls[ny][nx]
            if wall == Wall.CONCRETE:
                break
            pos = Position(nx, ny)
            flames.append(pos)
            if wall == Wall.BOX:
                boxes.append(pos)
                break

    return flames, boxes


def get_box_blast_tiles(
    state: Gamestate, blast_radius: int = DEFAULT_BLAST_RADIUS
) -> set[tuple[int, int]]:
    """
    Cached per-tick set of all empty tiles (x, y) from which a bomb with `blast_radius`
    would destroy at least one Wall.BOX.
    """
    global _box_adj_cache_key, _box_adj_cache_val
    key = (id(state), state.current_tick)
    if _box_adj_cache_key == key:
        return _box_adj_cache_val

    result: set[tuple[int, int]] = set()
    w, h = state.width, state.height
    walls = state.grid_walls

    for y in range(h):
        row = walls[y]
        for x in range(w):
            if row[x] == Wall.BOX:
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    for step in range(1, blast_radius + 1):
                        nx = x + dx * step
                        ny = y + dy * step
                        if not (0 <= nx < w and 0 <= ny < h):
                            break
                        w_type = walls[ny][nx]
                        if w_type != Wall.EMPTY:
                            break
                        result.add((nx, ny))

    _box_adj_cache_key = key
    _box_adj_cache_val = result
    return result


class SpaceTimeHazardModel:
    """
    Exact deterministic space-time hazard model for Temporal A* pathfinding and
    suicide-safety action masking.
    Tracks for every coordinate (x, y) across future ticks t = 1..horizon:
    - Lethal intervals [t_start, t_end] (from existing flames, bomb blasts, chain reactions,
      and Sudden Death tile collapses).
    - Bomb blocking intervals [1, t_exp] (bombs block movement until they detonate).
    - Box destruction times (boxes block movement until destroyed or cleared).
    """

    def __init__(self, state: Gamestate, extra_bomb_at_t1: Bomb | None = None) -> None:
        self.width = state.width
        self.height = state.height
        self.walls = state.grid_walls
        self.lethal_intervals: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.bomb_block_until: dict[tuple[int, int], int] = {}
        self.collapse_time: dict[tuple[int, int], int] = {}
        self.unsafe_coords: set[tuple[int, int]] = set()
        self.max_hazard_tick: int = 1

        # 1. Existing flames at t=0 remain lethal for 1 <= t <= f0 - 1
        for y in range(self.height):
            row = state.flames_grid[y]
            for x in range(self.width):
                f0 = row[x]
                if f0 > 1:
                    self._add_lethal((x, y), 1, f0 - 1)

        # 2. Bombs (existing bombs tick at t=1; extra_bomb placed at t=1 explodes at 1 + fuse)
        bombs: list[Bomb] = list(state.bombs)
        raw_exp_times: list[int] = [max(1, b.fuse_ticks) for b in bombs]

        if extra_bomb_at_t1 is not None:
            bombs.append(extra_bomb_at_t1)
            raw_exp_times.append(1 + extra_bomb_at_t1.fuse_ticks)

        if bombs:
            blast_by_idx: list[list[Position]] = []
            pos_to_indices: dict[tuple[int, int], list[int]] = {}
            for idx, b in enumerate(bombs):
                flames, _ = get_blast_rays(state, b.pos, b.blast_radius)
                blast_by_idx.append(flames)
                pos_to_indices.setdefault((b.pos.x, b.pos.y), []).append(idx)

            # Resolve chain explosion times
            changed = True
            while changed:
                changed = False
                for idx, flames in enumerate(blast_by_idx):
                    t_a = raw_exp_times[idx]
                    for fp in flames:
                        for other_idx in pos_to_indices.get((fp.x, fp.y), ()):
                            if t_a < raw_exp_times[other_idx]:
                                raw_exp_times[other_idx] = t_a
                                changed = True

            for idx, b in enumerate(bombs):
                t_exp = raw_exp_times[idx]
                b_coord = (b.pos.x, b.pos.y)
                prev_blk = self.bomb_block_until.get(b_coord, 0)
                if t_exp > prev_blk:
                    self.bomb_block_until[b_coord] = t_exp

                # When bomb explodes at t_exp, flames are lethal during [t_exp, t_exp + FLAME_DURATION_TICKS - 1]
                t_end = t_exp + FLAME_DURATION_TICKS - 1
                for fp in blast_by_idx[idx]:
                    self._add_lethal((fp.x, fp.y), t_exp, t_end)

        # 3. Sudden Death collapsing tiles within lookahead window
        lookahead_sd = max(self.max_hazard_tick + 4, DEFAULT_BOMB_FUSE + 3)
        for sx, sy, t_col in get_upcoming_sudden_death_tiles(state, lookahead=lookahead_sd):
            self.collapse_time[(sx, sy)] = t_col
            self._add_lethal((sx, sy), t_col, 999)

    def _add_lethal(self, coord: tuple[int, int], t_start: int, t_end: int) -> None:
        self.lethal_intervals.setdefault(coord, []).append((t_start, t_end))
        self.unsafe_coords.add(coord)
        if t_end < 500 and t_end > self.max_hazard_tick:
            self.max_hazard_tick = t_end

    def is_walkable_at(self, x: int, y: int, t: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if self.walls[y][x] != Wall.EMPTY:
            return False
        t_col = self.collapse_time.get((x, y))
        if t_col is not None and t >= t_col:
            return False
        blk_until = self.bomb_block_until.get((x, y))
        if blk_until is not None and t <= blk_until:
            return False
        return True

    def is_lethal_at(self, x: int, y: int, t: int) -> bool:
        for t_s, t_e in self.lethal_intervals.get((x, y), ()):
            if t_s <= t <= t_e:
                return True
        return False

    def is_permanently_safe_at(self, x: int, y: int, t: int) -> bool:
        if (x, y) in self.collapse_time:
            return False
        for t_s, t_e in self.lethal_intervals.get((x, y), ()):
            if t <= t_e:
                return False
        return True

    def heuristic(self, x: int, y: int) -> int:
        return 1 if (x, y) in self.unsafe_coords else 0


def get_spacetime_model(
    state: Gamestate, extra_bomb_at_t1: Bomb | None = None
) -> SpaceTimeHazardModel:
    global _spacetime_cache_key, _spacetime_cache_val
    if extra_bomb_at_t1 is None:
        key = (id(state), state.current_tick, len(state.bombs))
        if _spacetime_cache_key == key and _spacetime_cache_val is not None:
            return _spacetime_cache_val
        model = SpaceTimeHazardModel(state, extra_bomb_at_t1=None)
        _spacetime_cache_key = key
        _spacetime_cache_val = model
        return model
    return SpaceTimeHazardModel(state, extra_bomb_at_t1=extra_bomb_at_t1)


def temporal_astar_survives(
    model: SpaceTimeHazardModel, start_x: int, start_y: int, start_t: int = 1
) -> tuple[bool, int]:
    """
    Deterministic Temporal A* search over (x, y, t) space-time states.
    Checks whether a player at (start_x, start_y) at step `start_t` has a valid
    collision-free, flame-free trajectory to a permanently safe tile.
    Returns (can_survive, ticks_to_safety).
    """
    if model.is_lethal_at(start_x, start_y, start_t):
        return False, 999

    if model.is_permanently_safe_at(start_x, start_y, start_t):
        return True, 0

    max_t = model.max_hazard_tick + 2
    h0 = model.heuristic(start_x, start_y)
    # Priority queue of (f_score, g_ticks, x, y, t)
    open_heap: list[tuple[int, int, int, int, int]] = [
        (h0, 0, start_x, start_y, start_t)
    ]
    visited: set[tuple[int, int, int]] = {(start_x, start_y, start_t)}

    while open_heap:
        _, g, x, y, t = heapq.heappop(open_heap)

        if model.is_permanently_safe_at(x, y, t) or t >= max_t:
            return True, g

        next_t = t + 1
        # Candidate transitions at next_t: 4 cardinal moves + waiting in place (IDLE)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (0, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny, next_t) in visited:
                continue
            if (dx != 0 or dy != 0) and not model.is_walkable_at(nx, ny, next_t):
                continue
            if dx == 0 and dy == 0:
                # Waiting in place is valid as long as tile hasn't collapsed into concrete
                t_col = model.collapse_time.get((nx, ny))
                if t_col is not None and next_t >= t_col:
                    continue
            if model.is_lethal_at(nx, ny, next_t):
                continue

            visited.add((nx, ny, next_t))
            next_g = g + 1
            f_score = next_g + model.heuristic(nx, ny)
            heapq.heappush(open_heap, (f_score, next_g, nx, ny, next_t))

    return False, 999


def compute_danger_map(
    state: Gamestate, extra_bomb: Bomb | None = None
) -> dict[tuple[int, int], int]:
    """
    Returns a mapping from (x, y) -> ticks until explosion/fire/collapse.
    0 means currently on fire.
    >0 means a bomb (including chain explosions) or Sudden Death wall will hit in N ticks.
    Tiles not in the dict are completely safe.
    """
    global _danger_cache_key, _danger_cache_val
    if extra_bomb is None:
        key = (id(state), state.current_tick, len(state.bombs))
        if _danger_cache_key == key:
            return _danger_cache_val

    danger: dict[tuple[int, int], int] = {}

    for y in range(state.height):
        row = state.flames_grid[y]
        for x in range(state.width):
            if row[x] >= 0:
                danger[(x, y)] = 0

    for sx, sy, ticks_left in get_upcoming_sudden_death_tiles(
        state, lookahead=DEFAULT_BOMB_FUSE
    ):
        eff = max(1, ticks_left - 1) if extra_bomb is not None else ticks_left
        if (sx, sy) not in danger or eff < danger[(sx, sy)]:
            danger[(sx, sy)] = eff

    bombs = list(state.bombs)
    if extra_bomb is not None:
        bombs.append(extra_bomb)

    if not bombs:
        if extra_bomb is None:
            _danger_cache_key = (id(state), state.current_tick, len(state.bombs))
            _danger_cache_val = danger
        return danger

    blast_by_idx: list[list[Position]] = []
    pos_to_bomb_indices: dict[tuple[int, int], list[int]] = {}
    effective_fuses: list[int] = []

    for idx, b in enumerate(bombs):
        flames, _ = get_blast_rays(state, b.pos, b.blast_radius)
        blast_by_idx.append(flames)
        if extra_bomb is not None and b is not extra_bomb:
            effective_fuses.append(max(0, b.fuse_ticks - 1))
        else:
            effective_fuses.append(max(1, b.fuse_ticks))
        pos_to_bomb_indices.setdefault((b.pos.x, b.pos.y), []).append(idx)

    changed = True
    while changed:
        changed = False
        for idx, flames in enumerate(blast_by_idx):
            fuse_a = effective_fuses[idx]
            for fpos in flames:
                for other_idx in pos_to_bomb_indices.get((fpos.x, fpos.y), ()):
                    if fuse_a < effective_fuses[other_idx]:
                        effective_fuses[other_idx] = fuse_a
                        changed = True

    for idx, flames in enumerate(blast_by_idx):
        fuse = effective_fuses[idx]
        for fpos in flames:
            coord = (fpos.x, fpos.y)
            if coord not in danger or fuse < danger[coord]:
                danger[coord] = fuse

    if extra_bomb is None:
        _danger_cache_key = (id(state), state.current_tick, len(state.bombs))
        _danger_cache_val = danger
    return danger


def find_escape_actions(
    state: Gamestate, player: Player, extra_bomb: Bomb | None = None
) -> tuple[bool, set[Action], int]:
    """
    Uses Temporal A* over space-time to find which first-step actions allow
    `player` to survive and reach safety in minimum ticks.
    Returns (can_escape, best_first_actions, min_steps_to_safety).
    """
    model = get_spacetime_model(state, extra_bomb_at_t1=extra_bomb)
    px, py = player.pos.x, player.pos.y

    if extra_bomb is not None:
        # Placing a bomb keeps player at (px, py) at t=1
        ok, dist = temporal_astar_survives(model, px, py, start_t=1)
        return ok, ({Action.BOMB} if ok else set()), dist

    if model.is_permanently_safe_at(px, py, 1):
        return True, {Action.IDLE}, 0

    best_dist = 999
    best_actions: set[Action] = set()

    for act, (dx, dy, _) in DIRECTION_DELTAS.items():
        nx, ny = px + dx, py + dy
        if not is_walkable(state, nx, ny):
            continue
        ok, dist = temporal_astar_survives(model, nx, ny, start_t=1)
        if ok:
            total_d = 1 + dist
            if total_d < best_dist:
                best_dist = total_d
                best_actions = {act}
            elif total_d == best_dist:
                best_actions.add(act)

    if not best_actions:
        ok_idle, dist_idle = temporal_astar_survives(model, px, py, start_t=1)
        if ok_idle:
            return True, {Action.IDLE}, 1 + dist_idle
        return False, set(), 999

    return True, best_actions, best_dist


def create_initial_gamestate(
    width: int = 9,
    height: int = 9,
    controllers: list | None = None,
    box_density: float = 0.50,
    seed: int | None = None,
    fixed_layout: bool = False,
) -> Gamestate:
    """
    Creates a 9x9 Bomberman arena with 4 players in the 4 corners,
    concrete pillars at odd coordinates, L-shaped safe spawn zones in each corner,
    and destructible boxes in the middle.
    """
    rng = random.Random(seed) if seed is not None else random
    gs = Gamestate()
    gs.current_tick = 0
    gs.width = width
    gs.height = height
    gs.max_ticks = DEFAULT_MAX_TICKS
    gs.powerups = {}
    gs.sudden_death_index = 0

    spawn_corners = [
        (0, 0, Direction.DOWN),
        (width - 1, 0, Direction.DOWN),
        (0, height - 1, Direction.UP),
        (width - 1, height - 1, Direction.UP),
    ]

    safe_tiles: set[tuple[int, int]] = set()
    for sx, sy, _ in spawn_corners:
        safe_tiles.add((sx, sy))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = sx + dx, sy + dy
            if 0 <= nx < width and 0 <= ny < height:
                safe_tiles.add((nx, ny))

    gs.grid_walls = []
    for y in range(height):
        row: list[Wall] = []
        for x in range(width):
            if x % 2 == 1 and y % 2 == 1:
                row.append(Wall.CONCRETE)
            elif (x, y) in safe_tiles:
                row.append(Wall.EMPTY)
            elif fixed_layout:
                if (x + y) % 2 == 0 or (2 <= x <= width - 3 and 2 <= y <= height - 3):
                    row.append(Wall.BOX)
                else:
                    row.append(Wall.EMPTY)
            else:
                if rng.random() < box_density:
                    row.append(Wall.BOX)
                else:
                    row.append(Wall.EMPTY)
        gs.grid_walls.append(row)

    gs.flames_grid = [[-1 for _ in range(width)] for _ in range(height)]
    gs.flame_owners = [[-1 for _ in range(width)] for _ in range(height)]
    gs.bombs = []
    gs.players = []

    for idx, (sx, sy, facing) in enumerate(spawn_corners):
        ctrl = controllers[idx] if controllers and idx < len(controllers) else None
        p = Player(
            player_id=idx,
            pos=Position(sx, sy),
            facing=facing,
            alive=True,
            speed=1,
            bomb_capacity=1,
            active_bombs=0,
            blast_radius=DEFAULT_BLAST_RADIUS,
            controller=ctrl,
        )
        gs.players.append(p)

    reset_tick_cache()
    return gs


def _apply_powerup(player: Player, ptype: PowerUpType) -> None:
    if ptype == PowerUpType.BOMB_UP:
        player.bomb_capacity = min(4, player.bomb_capacity + 1)
    elif ptype == PowerUpType.FIRE_UP:
        player.blast_radius = min(5, player.blast_radius + 1)
    elif ptype == PowerUpType.SPEED_UP:
        player.speed = min(3, player.speed + 1)


def step_gamestate(
    state: Gamestate, actions_by_player: dict[int, list[Action]]
) -> dict[int, PlayerStepEvents]:
    """
    Advances the game state by 1 tick:
    1. Decrements existing flames.
    2. Ticks existing bombs.
    3. Places bombs for players requesting Action.BOMB.
    4. Moves players requesting directional actions & collects Power-Ups.
    5. Resolves explosions + chain explosions + box destruction + Power-Up drops.
    6. Applies Sudden Death arena shrinking (from SUDDEN_DEATH_START_TICK onward).
    7. Evaluates player deaths from flames/collapses and match completion.
    """
    reset_tick_cache()
    events: dict[int, PlayerStepEvents] = {
        p.id: PlayerStepEvents(player_id=p.id) for p in state.players
    }

    if state.is_over:
        return events

    state.current_tick += 1
    players_by_id = {p.id: p for p in state.players}

    # 1. Tick existing flames
    for y in range(state.height):
        for x in range(state.width):
            if state.flames_grid[y][x] > 0:
                state.flames_grid[y][x] -= 1
                if state.flames_grid[y][x] == 0:
                    state.flames_grid[y][x] = -1
                    state.flame_owners[y][x] = -1
            elif state.flames_grid[y][x] == 0:
                state.flames_grid[y][x] = -1
                state.flame_owners[y][x] = -1

    # 2. Tick existing bombs FIRST so newly placed bombs have full DEFAULT_BOMB_FUSE ticks
    exploding_queue: deque[Bomb] = deque()
    for b in state.bombs:
        b.fuse_ticks -= 1
        if b.fuse_ticks <= 0:
            exploding_queue.append(b)

    # 3. Process bomb placements
    for p in state.players:
        if not p.alive:
            continue
        p_actions = actions_by_player.get(p.id, [Action.IDLE])
        if Action.BOMB in p_actions:
            if (
                p.active_bombs < p.bomb_capacity
                and not has_bomb_at(state, p.pos.x, p.pos.y)
            ):
                new_bomb = Bomb(
                    id=state.next_bomb_id,
                    owner_id=p.id,
                    pos=p.pos,
                    fuse_ticks=DEFAULT_BOMB_FUSE,
                    blast_radius=p.blast_radius,
                )
                state.next_bomb_id += 1
                state.bombs.append(new_bomb)
                p.active_bombs += 1
                events[p.id].placed_bomb = True
            else:
                events[p.id].invalid_bomb = True

    # 4. Process player movements & powerup collection
    for p in state.players:
        p.prev_pos = p.pos
        if not p.alive:
            continue
        p_actions = actions_by_player.get(p.id, [Action.IDLE])
        move_act: Action | None = None
        for act in p_actions:
            if act in DIRECTION_DELTAS:
                move_act = act
                break

        if move_act is not None:
            dx, dy, new_facing = DIRECTION_DELTAS[move_act]
            p.facing = new_facing
            nx, ny = p.pos.x + dx, p.pos.y + dy
            if is_walkable(state, nx, ny):
                p.pos = Position(nx, ny)
                events[p.id].moved = True
            else:
                events[p.id].bumped_wall = True

        p_coord = (p.pos.x, p.pos.y)
        if p_coord in state.powerups:
            ptype = state.powerups.pop(p_coord)
            _apply_powerup(p, ptype)
            events[p.id].picked_powerup = True

    # 5. Resolve explosions (with chain explosions!)
    exploded_ids: set[int] = {b.id for b in exploding_queue}
    boxes_to_destroy: dict[tuple[int, int], int] = {}

    while exploding_queue:
        bomb = exploding_queue.popleft()
        owner = players_by_id.get(bomb.owner_id)
        if owner is not None and owner.active_bombs > 0:
            owner.active_bombs -= 1

        flame_positions, hit_boxes = get_blast_rays(state, bomb.pos, bomb.blast_radius)

        for fpos in flame_positions:
            fx, fy = fpos.x, fpos.y
            state.flames_grid[fy][fx] = FLAME_DURATION_TICKS
            state.flame_owners[fy][fx] = bomb.owner_id

            for other_bomb in state.bombs:
                if (
                    other_bomb.id not in exploded_ids
                    and other_bomb.pos.x == fx
                    and other_bomb.pos.y == fy
                ):
                    exploded_ids.add(other_bomb.id)
                    other_bomb.fuse_ticks = 0
                    exploding_queue.append(other_bomb)

        for bpos in hit_boxes:
            coord = (bpos.x, bpos.y)
            if coord not in boxes_to_destroy:
                boxes_to_destroy[coord] = bomb.owner_id

    if exploded_ids:
        state.bombs = [b for b in state.bombs if b.id not in exploded_ids]

    for (bx, by), owner_id in boxes_to_destroy.items():
        if state.grid_walls[by][bx] == Wall.BOX:
            state.grid_walls[by][bx] = Wall.EMPTY
            if owner_id in events:
                events[owner_id].boxes_destroyed += 1
            if owner_id in players_by_id:
                players_by_id[owner_id].boxes_destroyed += 1
            if random.random() < POWERUP_DROP_CHANCE:
                state.powerups[(bx, by)] = random.choice(ALL_POWERUPS)

    # 6. Sudden Death: gradually shrink the arena in a spiral from SUDDEN_DEATH_START_TICK
    if state.current_tick == SUDDEN_DEATH_START_TICK - 6:
        for y in range(1, state.height - 1):
            for x in range(1, state.width - 1):
                if state.grid_walls[y][x] == Wall.BOX and (
                    x in (1, state.width - 2) or y in (1, state.height - 2)
                ):
                    state.grid_walls[y][x] = Wall.EMPTY

    if state.current_tick >= SUDDEN_DEATH_START_TICK:
        spiral = get_spiral_coords(state.width, state.height)
        if state.sudden_death_index < len(spiral):
            sx, sy = spiral[state.sudden_death_index]
            state.sudden_death_index += 1
            state.grid_walls[sy][sx] = Wall.CONCRETE
            state.flames_grid[sy][sx] = -1
            state.powerups.pop((sx, sy), None)
            for b in list(state.bombs):
                if b.pos.x == sx and b.pos.y == sy:
                    owner = players_by_id.get(b.owner_id)
                    if owner is not None and owner.active_bombs > 0:
                        owner.active_bombs -= 1
                    state.bombs.remove(b)
            for p in state.players:
                if p.alive and p.pos.x == sx and p.pos.y == sy:
                    p.alive = False
                    events[p.id].died = True

    # 7. Evaluate player deaths from active flames
    for p in state.players:
        if not p.alive:
            continue
        if is_flame(state, p.pos.x, p.pos.y):
            p.alive = False
            events[p.id].died = True
            killer_id = state.flame_owners[p.pos.y][p.pos.x]
            if killer_id == p.id or killer_id < 0:
                events[p.id].suicided = True
            elif killer_id in events:
                events[killer_id].kills += 1
                if killer_id in players_by_id:
                    players_by_id[killer_id].kills += 1
        else:
            events[p.id].survived_tick = True

    # 8. Check match termination
    alive_players = [p for p in state.players if p.alive]
    if len(alive_players) <= 1:
        state.is_over = True
        if len(alive_players) == 1:
            winner = alive_players[0]
            state.winner_id = winner.id
            events[winner.id].won_match = True
        else:
            state.winner_id = None
    elif state.current_tick >= state.max_ticks:
        state.is_over = True
        state.winner_id = None

    reset_tick_cache()
    return events


class GameRules:
    clone = staticmethod(clone)
    reset_tick_cache = staticmethod(reset_tick_cache)
    is_in_bounds = staticmethod(is_in_bounds)
    has_bomb_at = staticmethod(has_bomb_at)
    is_walkable = staticmethod(is_walkable)
    is_flame = staticmethod(is_flame)
    get_blast_rays = staticmethod(get_blast_rays)
    get_box_blast_tiles = staticmethod(get_box_blast_tiles)
    get_spiral_coords = staticmethod(get_spiral_coords)
    get_upcoming_sudden_death_tiles = staticmethod(get_upcoming_sudden_death_tiles)
    get_spacetime_model = staticmethod(get_spacetime_model)
    temporal_astar_survives = staticmethod(temporal_astar_survives)
    compute_danger_map = staticmethod(compute_danger_map)
    find_escape_actions = staticmethod(find_escape_actions)
    create_initial_gamestate = staticmethod(create_initial_gamestate)
    step_gamestate = staticmethod(step_gamestate)
