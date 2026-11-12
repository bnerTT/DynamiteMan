from __future__ import annotations

from collections import deque
import os
import pickle
import random

from core.commands.gamerules import (
    DEFAULT_BOMB_FUSE,
    DIRECTION_DELTAS,
    PlayerStepEvents,
    SUDDEN_DEATH_START_TICK,
    compute_danger_map,
    find_escape_actions,
    get_box_blast_tiles,
    get_spacetime_model,
    has_bomb_at,
    is_walkable,
    temporal_astar_survives,
)
from core.entities.bomb import Bomb
from core.entities.player import Player
from core.vos.action import Action
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall

ALL_ACTIONS: tuple[Action, ...] = (
    Action.UP,
    Action.DOWN,
    Action.LEFT,
    Action.RIGHT,
    Action.BOMB,
    Action.IDLE,
)

MOVE_ACTIONS: tuple[Action, ...] = (
    Action.UP,
    Action.DOWN,
    Action.LEFT,
    Action.RIGHT,
)

# Discrete state tuple:
# (
#   in_danger: int        (0 = Safe, 1 = In Danger),
#   dir_up: int           (0 = Blocked/Suicidal, 1 = UnsafeSurvivable, 2 = SafeNeutral, 3 = BestEscapeOrTarget),
#   dir_down: int,
#   dir_left: int,
#   dir_right: int,
#   bomb_opportunity: int (0 = Cannot/SuicidalBomb, 1 = SurvivableEmptyBomb, 2 = SurvivableHitsBox, 3 = SurvivableHitsEnemy)
# )
StateTuple = tuple[int, int, int, int, int, int]


def _evaluate_bomb_at(
    state: Gamestate, player: Player, pos: Position
) -> tuple[bool, bool]:
    """
    Fast check whether a bomb placed at `pos` with `player.blast_radius` would
    effectively threaten an alive enemy or destroy any destructible box.
    Returns (hits_enemy, hits_box).
    """
    box_tiles = get_box_blast_tiles(state, player.blast_radius)
    hits_box = (pos.x, pos.y) in box_tiles

    hits_enemy = False
    px, py = pos.x, pos.y
    engage_range = min(2, player.blast_radius)

    for other in state.players:
        if other.alive and other.id != player.id:
            ox, oy = other.pos.x, other.pos.y
            if ox == px and abs(oy - py) <= engage_range:
                if oy == py:
                    hits_enemy = True
                    break
                step = 1 if oy > py else -1
                blocked = False
                for cy in range(py + step, oy, step):
                    if state.grid_walls[cy][px] != Wall.EMPTY:
                        blocked = True
                        break
                if not blocked:
                    hits_enemy = True
                    break
            elif oy == py and abs(ox - px) <= engage_range:
                step = 1 if ox > px else -1
                blocked = False
                for cx in range(px + step, ox, step):
                    if state.grid_walls[py][cx] != Wall.EMPTY:
                        blocked = True
                        break
                if not blocked:
                    hits_enemy = True
                    break

    return hits_enemy, hits_box


def _find_best_target_actions(
    state: Gamestate,
    player: Player,
    danger: dict[tuple[int, int], int],
    safe_move_actions: set[Action],
) -> set[Action]:
    """
    Uses fast BFS starting ONLY from Temporal-A*-verified safe first steps
    to find the shortest path toward the highest-priority target
    (inner 5x5 cage during Sudden Death, power-up, enemy, or box).
    """
    if not safe_move_actions:
        return set()

    start = (player.pos.x, player.pos.y)
    box_tiles = get_box_blast_tiles(state, player.blast_radius)
    powerup_tiles = set(state.powerups.keys())
    enemies = [
        (p.pos.x, p.pos.y)
        for p in state.players
        if p.alive and p.id != player.id
    ]

    enemy_attack_tiles: set[tuple[int, int]] = set()
    for ex, ey in enemies:
        enemy_attack_tiles.add((ex, ey))
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = ex + dx, ey + dy
            if 0 <= nx < state.width and 0 <= ny < state.height:
                if state.grid_walls[ny][nx] == Wall.EMPTY:
                    enemy_attack_tiles.add((nx, ny))

    queue: deque[tuple[int, int, int, Action]] = deque()
    visited: set[tuple[int, int]] = {start}

    for act in MOVE_ACTIONS:
        if act not in safe_move_actions:
            continue
        dx, dy, _ = DIRECTION_DELTAS[act]
        nx, ny = start[0] + dx, start[1] + dy
        if (nx, ny) in danger:
            continue
        visited.add((nx, ny))
        queue.append((nx, ny, 1, act))

    best_actions: set[Action] = set()
    best_score: float = -1.0

    outside_inner_cage = (
        state.current_tick >= SUDDEN_DEATH_START_TICK - 16
        and not (2 <= start[0] <= state.width - 3 and 2 <= start[1] <= state.height - 3)
    )

    while queue:
        x, y, dist, first_act = queue.popleft()
        coord = (x, y)

        tile_score = 0.0
        if outside_inner_cage and (
            2 <= x <= state.width - 3 and 2 <= y <= state.height - 3
        ):
            tile_score = 300.0 / (dist + 1)
        elif coord in powerup_tiles:
            tile_score = 140.0 / (dist + 0.5)
        elif coord in enemy_attack_tiles:
            tile_score = 115.0 / (dist + 1)
        elif coord in box_tiles:
            tile_score = 60.0 / (dist + 1)

        if tile_score > best_score + 1e-6:
            best_score = tile_score
            best_actions = {first_act}
        elif abs(tile_score - best_score) <= 1e-6 and tile_score > 0:
            best_actions.add(first_act)

        if best_score >= 60.0 and dist >= 4:
            break

        for act in MOVE_ACTIONS:
            dx, dy, _ = DIRECTION_DELTAS[act]
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited:
                continue
            if not is_walkable(state, nx, ny):
                continue
            if (nx, ny) in danger:
                continue
            visited.add((nx, ny))
            queue.append((nx, ny, dist + 1, first_act))

    if not best_actions:
        cx, cy = state.width // 2, state.height // 2
        best_dist = 999
        for act in safe_move_actions:
            dx, dy, _ = DIRECTION_DELTAS[act]
            nx, ny = start[0] + dx, start[1] + dy
            if enemies and not outside_inner_cage:
                d = min(abs(nx - ex) + abs(ny - ey) for ex, ey in enemies)
            else:
                d = abs(nx - cx) + abs(ny - cy)
            if d < best_dist:
                best_dist = d
                best_actions = {act}
            elif d == best_dist:
                best_actions.add(act)

    return best_actions


def extract_state_and_mask(
    state: Gamestate, player_id: int
) -> tuple[StateTuple, list[bool]]:
    """
    Uses the Temporal A* space-time hazard model to compute:
      1. `state_tuple`: 6-element discrete state representation distinguishing
         Suicidal/Blocked (0), Unsafe but Survivable (1), Safe Neutral (2), and Best Path (3).
      2. `action_mask`: 6-element boolean list corresponding to `ALL_ACTIONS`
         (`UP, DOWN, LEFT, RIGHT, BOMB, IDLE`) that ONLY masks out illegal or
         deterministically SUICIDAL actions (where Temporal A* proves no survival
         path exists). Unsafe/risky actions that are still survivable remain
         UNMASKED (True) so the Q-Learning agent learns to avoid them via rewards!
    """
    player: Player | None = None
    for p in state.players:
        if p.id == player_id:
            player = p
            break

    if player is None or not player.alive:
        return (0, 0, 0, 0, 0, 0), [False, False, False, False, False, True]

    danger = compute_danger_map(state)
    model = get_spacetime_model(state, extra_bomb_at_t1=None)
    px, py = player.pos.x, player.pos.y

    in_danger = (
        0
        if model.is_permanently_safe_at(px, py, 1) and (px, py) not in danger
        else 1
    )

    # 1. Evaluate Temporal A* survival for each of the 4 movement actions + IDLE
    #    ONLY mask out an action if it is illegal (wall/bomb) or SUICIDAL (survives == False).
    action_mask: list[bool] = [False] * len(ALL_ACTIONS)
    escape_dists: dict[Action, int] = {}
    survivable_moves: set[Action] = set()
    completely_safe_moves: set[Action] = set()

    for idx, act in enumerate(MOVE_ACTIONS):
        dx, dy, _ = DIRECTION_DELTAS[act]
        nx, ny = px + dx, py + dy
        if not is_walkable(state, nx, ny):
            action_mask[idx] = False
            continue
        survives, ticks_to_safe = temporal_astar_survives(model, nx, ny, start_t=1)
        if survives:
            # Not suicidal! Keep unmasked even if (nx, ny) is currently in a blast ray (unsafe)
            action_mask[idx] = True
            survivable_moves.add(act)
            escape_dists[act] = 1 + ticks_to_safe
            if (nx, ny) not in danger:
                completely_safe_moves.add(act)

    # Evaluate IDLE survival at (px, py, t=1)
    idle_survives, _ = temporal_astar_survives(model, px, py, start_t=1)
    if idle_survives:
        action_mask[5] = True

    # 2. Evaluate Temporal A* survival for placing a new bomb (Action.BOMB at index 4)
    #    If placing a bomb is legal and NOT suicidal (bomb_survives == True),
    #    action_mask[4] is True (even if it hits nothing, which is bomb_opportunity=1).
    bomb_opportunity = 0
    if (
        player.active_bombs < player.bomb_capacity
        and not has_bomb_at(state, px, py)
    ):
        hypothetical_bomb = Bomb(
            id=-1,
            owner_id=player.id,
            pos=player.pos,
            fuse_ticks=DEFAULT_BOMB_FUSE,
            blast_radius=player.blast_radius,
        )
        bomb_model = get_spacetime_model(state, extra_bomb_at_t1=hypothetical_bomb)
        bomb_survives, _ = temporal_astar_survives(bomb_model, px, py, start_t=1)
        if bomb_survives:
            action_mask[4] = True
            hits_enemy, hits_box = _evaluate_bomb_at(state, player, player.pos)
            if hits_enemy:
                bomb_opportunity = 3
            elif hits_box:
                bomb_opportunity = 2
            else:
                bomb_opportunity = 1  # Survivable bomb, but hits nothing (useless/unsafe)

    # Fallback: if completely cornered by enemy bombs and all 6 actions are suicidal,
    # unmask any walkable move or IDLE so the controller still returns a valid Action
    if not any(action_mask):
        for idx, act in enumerate(MOVE_ACTIONS):
            dx, dy, _ = DIRECTION_DELTAS[act]
            if is_walkable(state, px + dx, py + dy):
                action_mask[idx] = True
        if not any(action_mask):
            action_mask[5] = True

    # 3. Determine preferred actions for state feature representation
    if in_danger > 0 and escape_dists:
        min_esc = min(escape_dists.values())
        preferred_actions = {
            act for act, d in escape_dists.items() if d == min_esc
        }
    elif bomb_opportunity in (2, 3):
        preferred_actions = set()
    else:
        preferred_actions = _find_best_target_actions(
            state, player, danger, completely_safe_moves
        )

    # 4. Classify each of the 4 cardinal directions into 4 distinct levels:
    #    0 = Blocked or Suicidal (Masked out)
    #    1 = Unsafe / In Blast Zone (Unmasked & Survivable, but risky/detour!)
    #    2 = Safe Neutral Tile (Unmasked, outside blast zones)
    #    3 = Best Escape Route (if in_danger=1) or Best Target Path (if in_danger=0)
    dir_features: list[int] = []
    for idx, act in enumerate(MOVE_ACTIONS):
        dx, dy, _ = DIRECTION_DELTAS[act]
        nx, ny = px + dx, py + dy
        if not action_mask[idx]:
            dir_features.append(0)
        elif act in preferred_actions:
            dir_features.append(3)
        elif in_danger > 0 or (nx, ny) in danger:
            dir_features.append(1)  # Unsafe (in blast zone or slower escape), but NOT suicidal!
        else:
            dir_features.append(2)  # Safe neutral tile

    state_tuple: StateTuple = (
        in_danger,
        dir_features[0],
        dir_features[1],
        dir_features[2],
        dir_features[3],
        bomb_opportunity,
    )
    return state_tuple, action_mask


def extract_state(state: Gamestate, player_id: int) -> StateTuple:
    state_tuple, _ = extract_state_and_mask(state, player_id)
    return state_tuple


def get_safe_action_mask(state: Gamestate, player_id: int) -> list[bool]:
    _, mask = extract_state_and_mask(state, player_id)
    return mask


def compute_reward(
    events: PlayerStepEvents,
    prev_state: StateTuple,
    action: Action,
    next_state: StateTuple,
) -> float:
    """
    Shapes the reinforcement learning reward signal for Tabular Q-Learning.
    Since suicidal actions are masked out by Temporal A*, the agent explores
    among safe and unsafe-but-survivable actions and learns through rewards to
    avoid unsafe tiles (dir=1) and empty bombs (bomb_opp=1).
    """
    reward = 0.0

    if events.died:
        if events.suicided:
            return -150.0
        return -110.0

    if events.won_match:
        reward += 100.0

    if events.kills > 0:
        reward += 85.0 * events.kills

    if events.boxes_destroyed > 0:
        reward += 22.0 * events.boxes_destroyed

    if events.picked_powerup:
        reward += 25.0

    in_danger, d_up, d_down, d_left, d_right, bomb_opp = prev_state
    dir_map = {
        Action.UP: d_up,
        Action.DOWN: d_down,
        Action.LEFT: d_left,
        Action.RIGHT: d_right,
    }

    if action == Action.BOMB:
        if events.invalid_bomb or bomb_opp == 0:
            reward -= 50.0
        elif bomb_opp == 1:
            # Survivable bomb, but hits nothing (wasteful / creates self-hazard)
            reward -= 18.0
        elif bomb_opp == 2:
            # Survivable bomb that hits a destructible box!
            reward += 28.0
        elif bomb_opp == 3:
            # Survivable bomb that threatens an enemy!
            reward += 45.0

    elif action in dir_map:
        d_status = dir_map[action]
        if events.bumped_wall or d_status == 0:
            reward -= 40.0
        elif d_status == 1:
            # Stepped onto an UNSAFE (blast-zone / non-minimal escape) tile!
            reward -= 22.0
        elif d_status == 3:
            if in_danger > 0:
                reward += 26.0
            else:
                reward += 7.0
        elif d_status == 2:
            if bomb_opp in (2, 3):
                reward -= 6.0
            elif 3 in (d_up, d_down, d_left, d_right):
                reward -= 3.0
            else:
                reward += 2.0

    elif action == Action.IDLE:
        if in_danger > 0:
            reward -= 30.0
        elif bomb_opp in (2, 3):
            reward -= 10.0
        elif 3 in (d_up, d_down, d_left, d_right):
            reward -= 5.0
        else:
            reward += 4.0

    if prev_state[0] > 0 and next_state[0] == 0:
        reward += 20.0
    elif prev_state[0] == 0 and next_state[0] > 0 and action != Action.BOMB:
        reward -= 25.0

    return reward


class QLearningAgent:
    """
    Tabular Q-Learning Agent with Temporal A* Suicide-Safety Action Masking.
    All 4 AI players share a single QLearningAgent instance during self-play
    so the Q-table collects 4x experience per match.

    Bellman Update Equation (with action masking over safe actions A_safe(s')):
        Q(s, a) <- Q(s, a) + alpha * (reward + gamma * max_{a' in A_safe(s')} Q(s', a') - Q(s, a))
    """

    def __init__(
        self,
        alpha: float = 0.20,
        gamma: float = 0.90,
        epsilon: float = 1.0,
        epsilon_min: float = 0.02,
        epsilon_decay: float = 0.996,
    ) -> None:
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.q_table: dict[StateTuple, list[float]] = {}
        self.total_updates: int = 0
        self.episodes_trained: int = 0

    def _get_q_values(self, state: StateTuple) -> list[float]:
        q_vals = self.q_table.get(state)
        if q_vals is None:
            q_vals = [0.0] * len(ALL_ACTIONS)
            self.q_table[state] = q_vals
        return q_vals

    def choose_action_from_state(
        self,
        state: StateTuple,
        training: bool = False,
        action_mask: list[bool] | None = None,
    ) -> Action:
        valid_indices = (
            [i for i, allowed in enumerate(action_mask) if allowed]
            if action_mask is not None and any(action_mask)
            else list(range(len(ALL_ACTIONS)))
        )

        if training and random.random() < self.epsilon:
            return ALL_ACTIONS[random.choice(valid_indices)]

        q_vals = self._get_q_values(state)
        max_q = max(q_vals[i] for i in valid_indices)
        best_indices = [
            i for i in valid_indices if abs(q_vals[i] - max_q) <= 1e-7
        ]
        chosen_idx = random.choice(best_indices)
        return ALL_ACTIONS[chosen_idx]

    def choose_action(
        self, gamestate: Gamestate, player_id: int, training: bool = False
    ) -> Action:
        state_tuple, action_mask = extract_state_and_mask(gamestate, player_id)
        return self.choose_action_from_state(
            state_tuple, training=training, action_mask=action_mask
        )

    def update(
        self,
        state: StateTuple,
        action: Action,
        reward: float,
        next_state: StateTuple,
        done: bool,
        next_action_mask: list[bool] | None = None,
    ) -> None:
        action_idx = ALL_ACTIONS.index(action)
        q_vals = self._get_q_values(state)
        current_q = q_vals[action_idx]

        if done:
            target_q = reward
        else:
            next_q_vals = self._get_q_values(next_state)
            if next_action_mask is not None and any(next_action_mask):
                max_next_q = max(
                    next_q_vals[i]
                    for i, allowed in enumerate(next_action_mask)
                    if allowed
                )
            else:
                max_next_q = max(next_q_vals)
            target_q = reward + self.gamma * max_next_q

        q_vals[action_idx] = current_q + self.alpha * (target_q - current_q)
        self.total_updates += 1

    def decay_epsilon(self) -> None:
        self.episodes_trained += 1
        if self.epsilon > self.epsilon_min:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        payload = {
            "q_table": self.q_table,
            "alpha": self.alpha,
            "gamma": self.gamma,
            "epsilon": self.epsilon,
            "epsilon_min": self.epsilon_min,
            "epsilon_decay": self.epsilon_decay,
            "total_updates": self.total_updates,
            "episodes_trained": self.episodes_trained,
        }
        with open(filepath, "wb") as f:
            pickle.dump(payload, f)

    def load(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        with open(filepath, "rb") as f:
            payload = pickle.load(f)
        self.q_table = payload.get("q_table", {})
        self.alpha = payload.get("alpha", self.alpha)
        self.gamma = payload.get("gamma", self.gamma)
        self.epsilon = payload.get("epsilon", self.epsilon_min)
        self.total_updates = payload.get("total_updates", 0)
        self.episodes_trained = payload.get("episodes_trained", 0)
        return True


class RandomAgent:
    """
    Baseline agent that chooses random actions.
    """

    def choose_action(
        self, state: Gamestate, player_id: int, training: bool = False
    ) -> Action:
        return random.choices(
            ALL_ACTIONS, weights=[22, 22, 22, 22, 6, 6], k=1
        )[0]


class HeuristicHumanLikeAgent:
    """
    Simulates a casual human player for benchmarking the Q-Learning agent:
    - Dodges active bombs when it notices danger,
    - Walks toward power-ups, boxes, or enemies and plants bombs,
    - Has realistic human reaction speed (occasionally hesitates for a tick,
      or misses multi-step chain/corner lookahead).
    """

    def __init__(self, hesitation_prob: float = 0.25) -> None:
        self.hesitation_prob = hesitation_prob

    def choose_action(
        self, gamestate: Gamestate, player_id: int, training: bool = False
    ) -> Action:
        player = next((p for p in gamestate.players if p.id == player_id), None)
        if player is None or not player.alive:
            return Action.IDLE

        danger = compute_danger_map(gamestate)
        px, py = player.pos.x, player.pos.y

        if (px, py) in danger:
            if random.random() < 0.12:
                return Action.IDLE
            _, escape_acts, _ = find_escape_actions(gamestate, player)
            if escape_acts and Action.IDLE not in escape_acts:
                return random.choice(list(escape_acts))
            valid_moves = []
            for act in MOVE_ACTIONS:
                dx, dy, _ = DIRECTION_DELTAS[act]
                nx, ny = px + dx, py + dy
                if is_walkable(gamestate, nx, ny) and danger.get((nx, ny), 99) > 1:
                    valid_moves.append(act)
            return random.choice(valid_moves) if valid_moves else Action.IDLE

        if random.random() < self.hesitation_prob:
            return Action.IDLE

        hits_enemy, hits_box = _evaluate_bomb_at(gamestate, player, player.pos)
        if (
            (hits_enemy or hits_box)
            and player.active_bombs < player.bomb_capacity
            and not has_bomb_at(gamestate, px, py)
        ):
            adj_open = sum(
                1
                for act in MOVE_ACTIONS
                if is_walkable(
                    gamestate,
                    px + DIRECTION_DELTAS[act][0],
                    py + DIRECTION_DELTAS[act][1],
                )
            )
            if adj_open >= 1 and random.random() < 0.65:
                return Action.BOMB

        safe_moves = []
        for act in MOVE_ACTIONS:
            dx, dy, _ = DIRECTION_DELTAS[act]
            nx, ny = px + dx, py + dy
            if is_walkable(gamestate, nx, ny) and (nx, ny) not in danger:
                if (nx, ny) in gamestate.powerups:
                    return act
                safe_moves.append(act)

        if safe_moves:
            return random.choice(safe_moves)
        return Action.IDLE
