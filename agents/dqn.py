from __future__ import annotations

from collections import deque
import os
import pickle
import random

import numpy as np

from agents.qlearning import (
    ALL_ACTIONS,
    MOVE_ACTIONS,
    _evaluate_bomb_at,
)
from core.commands.gamerules import (
    DEFAULT_BOMB_FUSE,
    DIRECTION_DELTAS,
    PlayerStepEvents,
    SUDDEN_DEATH_START_TICK,
    compute_danger_map,
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
from core.vos.walls import Wall


def extract_dqn_features_and_mask(
    state: Gamestate, player_id: int
) -> tuple[np.ndarray, list[bool], dict[str, float]]:
    """
    Extracts:
      1. `features`: A 1D float32 NumPy vector encoding the raw 9x9 multi-channel
         board state + egocentric 5x5 local neighborhood + 4-directional ray
         sensors + player stats (WITHOUT calling `_find_best_target_actions`).
      2. `action_mask`: 6-element boolean list for `ALL_ACTIONS`
         (`UP, DOWN, LEFT, RIGHT, BOMB, IDLE`) using Temporal A* that ONLY masks
         out illegal or deterministically SUICIDAL actions (`survives == False`).
         Unsafe/risky actions that are still survivable remain UNMASKED (`True`)
         so the Deep Q-Network learns to avoid them via Q-value updates!
      3. `aux_info`: Diagnostic dictionary used for reward shaping during training
         (e.g., whether player is in a blast zone, ticks to safety, bomb value).
    """
    w, h = state.width, state.height
    player: Player | None = None
    for p in state.players:
        if p.id == player_id:
            player = p
            break

    # Feature vector layout:
    # - 5 channels of 9x9 full board (5 * 81 = 405):
    #     ch0: wall/box map (-1.0 concrete, 0.5 destructible box, 0.0 empty)
    #     ch1: bomb & flame danger intensity (0.0 safe -> 1.0 imminent explosion/flame)
    #     ch2: powerups (1.0 where powerup exists)
    #     ch3: self position (1.0 at player pos)
    #     ch4: alive enemy positions (1.0 at enemy pos)
    # - 3 channels of egocentric 5x5 window centered on player (3 * 25 = 75):
    #     local walkability, local danger intensity, local targets (boxes/enemies/powerups)
    # - 28 structured egocentric & ray sensors:
    #     - 4 cardinal neighbors: [is_walkable, danger_intensity, escape_urgency,
    #       ray_box_dist, ray_enemy_dist, ray_powerup_dist] (4 * 6 = 24)
    #     - 4 global/self stats: [in_danger, can_place_bomb, bomb_hits_box, bomb_hits_enemy]
    # Total dimension = 405 + 75 + 28 = 508 float32 features
    feature_dim = 5 * w * h + 3 * 25 + 28
    if player is None or not player.alive:
        return (
            np.zeros(feature_dim, dtype=np.float32),
            [False, False, False, False, False, True],
            {"in_danger": 0.0, "ticks_to_safe": 0.0, "bomb_opp": 0.0, "potential": 0.0},
        )

    danger = compute_danger_map(state)
    model = get_spacetime_model(state, extra_bomb_at_t1=None)
    px, py = player.pos.x, player.pos.y

    cur_survives, cur_ticks_to_safe = temporal_astar_survives(model, px, py, start_t=0)
    in_danger = (
        0.0
        if model.is_permanently_safe_at(px, py, 1) and (px, py) not in danger
        else 1.0
    )

    # 1. Temporal A* Suicide-Safety Action Mask (UNSAFE != SUICIDAL)
    action_mask: list[bool] = [False] * len(ALL_ACTIONS)
    neighbor_ticks_to_safe: list[float] = [8.0] * 4

    for idx, act in enumerate(MOVE_ACTIONS):
        dx, dy, _ = DIRECTION_DELTAS[act]
        nx, ny = px + dx, py + dy
        if not is_walkable(state, nx, ny):
            action_mask[idx] = False
            continue
        survives, t_safe = temporal_astar_survives(model, nx, ny, start_t=1)
        if survives:
            # UNSAFE != SUICIDAL: keep unmasked even if (nx, ny) is inside `danger`!
            action_mask[idx] = True
            neighbor_ticks_to_safe[idx] = float(t_safe)

    idle_survives, idle_t_safe = temporal_astar_survives(model, px, py, start_t=1)
    if idle_survives:
        action_mask[5] = True

    bomb_opp = 0
    hits_enemy, hits_box = False, False
    if player.active_bombs < player.bomb_capacity and not has_bomb_at(state, px, py):
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
                bomb_opp = 3
            elif hits_box:
                bomb_opp = 2
            else:
                bomb_opp = 1  # Survivable empty bomb (unmasked!)

    if not any(action_mask):
        for idx, act in enumerate(MOVE_ACTIONS):
            dx, dy, _ = DIRECTION_DELTAS[act]
            if is_walkable(state, px + dx, py + dy):
                action_mask[idx] = True
        if not any(action_mask):
            action_mask[5] = True

    # 2. Build raw 9x9 multi-channel spatial grid (5 channels x 9 x 9 = 405)
    grid_channels = np.zeros((5, h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            wt = state.grid_walls[y][x]
            if wt == Wall.CONCRETE:
                grid_channels[0, y, x] = -1.0
            elif wt == Wall.BOX:
                grid_channels[0, y, x] = 0.5

            if state.flames_grid[y][x] >= 0:
                grid_channels[1, y, x] = 1.0
            elif (x, y) in danger:
                fuse = danger[(x, y)]
                grid_channels[1, y, x] = max(
                    0.15, 1.0 - (float(fuse) / float(DEFAULT_BOMB_FUSE + 1))
                )

    for (ux, uy) in state.powerups:
        if 0 <= ux < w and 0 <= uy < h:
            grid_channels[2, uy, ux] = 1.0

    grid_channels[3, py, px] = 1.0
    enemies: list[tuple[int, int]] = []
    for other in state.players:
        if other.alive and other.id != player.id:
            grid_channels[4, other.pos.y, other.pos.x] = 1.0
            enemies.append((other.pos.x, other.pos.y))

    # 3. Build egocentric 5x5 local patch around (px, py) (3 channels x 5 x 5 = 75)
    local_patch = np.zeros((3, 5, 5), dtype=np.float32)
    for dy_i, dy in enumerate(range(-2, 3)):
        for dx_i, dx in enumerate(range(-2, 3)):
            nx, ny = px + dx, py + dy
            if 0 <= nx < w and 0 <= ny < h:
                local_patch[0, dy_i, dx_i] = (
                    1.0 if is_walkable(state, nx, ny) else -1.0
                )
                local_patch[1, dy_i, dx_i] = grid_channels[1, ny, nx]
                if (nx, ny) in state.powerups:
                    local_patch[2, dy_i, dx_i] = 1.0
                elif grid_channels[4, ny, nx] > 0:
                    local_patch[2, dy_i, dx_i] = 0.8
                elif state.grid_walls[ny][nx] == Wall.BOX:
                    local_patch[2, dy_i, dx_i] = 0.5
            else:
                local_patch[0, dy_i, dx_i] = -1.0
                local_patch[1, dy_i, dx_i] = 1.0

    # 4. Build 28 directional & self sensors (using raw coordinate distances / rays, NO BFS)
    sensors = np.zeros(28, dtype=np.float32)
    box_blast_tiles = get_box_blast_tiles(state, player.blast_radius)
    powerup_coords = list(state.powerups.keys())
    sd_active = state.current_tick >= SUDDEN_DEATH_START_TICK - 16
    cx, cy = w // 2, h // 2

    min_t_safe = min(neighbor_ticks_to_safe) if any(action_mask[:4]) else 8.0

    for idx, act in enumerate(MOVE_ACTIONS):
        dx, dy, _ = DIRECTION_DELTAS[act]
        nx, ny = px + dx, py + dy
        base = idx * 6

        if not action_mask[idx]:
            sensors[base + 0] = -1.0  # Blocked or suicidal
            sensors[base + 1] = 1.0   # Maximum danger
            sensors[base + 2] = -1.0
            continue

        sensors[base + 0] = 1.0
        # Immediate tile danger level (0.0 if safe, >0 if in blast ray)
        tile_danger = grid_channels[1, ny, nx]
        sensors[base + 1] = tile_danger

        # Escape urgency: +1.0 if this move is the fastest way out of danger
        if in_danger > 0.0:
            sensors[base + 2] = (
                1.0
                if abs(neighbor_ticks_to_safe[idx] - min_t_safe) <= 1e-5
                else -0.5
            )
        else:
            sensors[base + 2] = 0.5 if tile_danger == 0.0 else -0.8

        # Directional cosine/Manhattan alignment to nearest powerup, enemy, and box/cage
        if powerup_coords:
            cur_d = min(abs(px - ux) + abs(py - uy) for ux, uy in powerup_coords)
            nxt_d = min(abs(nx - ux) + abs(ny - uy) for ux, uy in powerup_coords)
            sensors[base + 3] = float(cur_d - nxt_d)
        if enemies:
            cur_d = min(abs(px - ex) + abs(py - ey) for ex, ey in enemies)
            nxt_d = min(abs(nx - ex) + abs(ny - ey) for ex, ey in enemies)
            sensors[base + 4] = float(cur_d - nxt_d)
        if sd_active and not (2 <= px <= w - 3 and 2 <= py <= h - 3):
            cur_d = abs(px - cx) + abs(py - cy)
            nxt_d = abs(nx - cx) + abs(ny - cy)
            sensors[base + 5] = float(cur_d - nxt_d)
        elif box_blast_tiles:
            cur_d = min(abs(px - bx) + abs(py - by) for bx, by in box_blast_tiles)
            nxt_d = min(abs(nx - bx) + abs(ny - by) for bx, by in box_blast_tiles)
            sensors[base + 5] = float(cur_d - nxt_d)

    sensors[24] = in_danger
    sensors[25] = 1.0 if action_mask[4] else 0.0
    sensors[26] = 1.0 if hits_box else 0.0
    sensors[27] = 1.0 if hits_enemy else 0.0

    features = np.concatenate(
        [grid_channels.ravel(), local_patch.ravel(), sensors]
    ).astype(np.float32)

    # Compute spatial potential for dense reward shaping during training
    potential = 0.0
    if sd_active and not (2 <= px <= w - 3 and 2 <= py <= h - 3):
        potential -= 2.5 * (abs(px - cx) + abs(py - cy))
    else:
        if powerup_coords:
            d_pu = min(abs(px - ux) + abs(py - uy) for ux, uy in powerup_coords)
            potential -= 1.8 * d_pu
        if enemies:
            d_en = min(abs(px - ex) + abs(py - ey) for ex, ey in enemies)
            potential -= 1.2 * d_en
        if box_blast_tiles:
            d_bx = min(abs(px - bx) + abs(py - by) for bx, by in box_blast_tiles)
            potential -= 0.9 * d_bx

    aux_info = {
        "in_danger": in_danger,
        "ticks_to_safe": float(cur_ticks_to_safe if cur_survives else 8.0),
        "idle_ticks_to_safe": float(idle_t_safe if idle_survives else 8.0),
        "bomb_opp": float(bomb_opp),
        "potential": potential,
    }
    return features, action_mask, aux_info


def compute_dqn_reward(
    events: PlayerStepEvents,
    prev_aux: dict[str, float],
    action: Action,
    next_aux: dict[str, float],
) -> float:
    """
    Computes the RL reward for the Deep Q-Network agent.
    Since UNSAFE != SUICIDAL actions remain unmasked, the DQN learns from
    these rewards to:
      1. Avoid stepping onto or idling on unsafe blast tiles,
      2. Escape blast zones along the fastest path,
      3. Only drop bombs when they hit destructible boxes or threaten enemies
         (and avoid dropping useless empty bombs),
      4. Navigate toward powerups, boxes, enemies, and the Sudden Death safe zone.
    """
    if events.died:
        return -150.0 if events.suicided else -110.0

    reward = 0.0
    if events.won_match:
        reward += 100.0
    if events.kills > 0:
        reward += 85.0 * events.kills
    if events.boxes_destroyed > 0:
        reward += 24.0 * events.boxes_destroyed
    if events.picked_powerup:
        reward += 28.0

    prev_danger = prev_aux["in_danger"]
    next_danger = next_aux["in_danger"]
    bomb_opp = int(prev_aux["bomb_opp"])

    if action == Action.BOMB:
        if events.invalid_bomb or bomb_opp == 0:
            reward -= 45.0
        elif bomb_opp == 1:
            # Survivable bomb, but hits nothing (unmasked unsafe/wasteful action!)
            reward -= 22.0
        elif bomb_opp == 2:
            reward += 30.0
        elif bomb_opp == 3:
            reward += 48.0
    elif action in MOVE_ACTIONS:
        if events.bumped_wall:
            reward -= 35.0
        elif prev_danger > 0.0:
            if next_danger == 0.0:
                reward += 28.0
            elif next_aux["ticks_to_safe"] < prev_aux["ticks_to_safe"]:
                reward += 18.0
            else:
                reward -= 20.0
        else:
            if next_danger > 0.0:
                # Stepped from a safe tile into an active blast ray (unsafe!)
                reward -= 26.0
            else:
                # Potential-based shaping toward targets
                delta_pot = next_aux["potential"] - prev_aux["potential"]
                reward += 3.5 * delta_pot
                if bomb_opp in (2, 3):
                    reward -= 6.0
    elif action == Action.IDLE:
        if prev_danger > 0.0:
            reward -= 30.0
        elif bomb_opp in (2, 3):
            reward -= 12.0
        else:
            reward -= 2.0

    return reward


class DQNAgent:
    """
    Deep Q-Network (Dueling Double-DQN) Agent implemented in vectorized NumPy.
    Architecture:
        Input (508 features: 9x9 multi-channel grid + 5x5 egocentric patch + ray sensors)
          -> Linear(508, 128) + ReLU
          -> Linear(128, 64) + ReLU
          -> Dueling Heads:
               Value Stream V(s): Linear(64, 1)
               Advantage Stream A(s, a): Linear(64, 6)
               Q(s, a) = V(s) + (A(s, a) - mean_a A(s, a))

    Includes:
      - Experience Replay Buffer (`deque` of transitions)
      - Target Network with periodic/Polyak updates
      - Adam Optimizer with Huber (smooth L1) loss
      - Temporal A* Suicide-Safety Action Masking (`UNSAFE != SUICIDAL`)
    """

    def __init__(
        self,
        input_dim: int = 508,
        hidden1: int = 128,
        hidden2: int = 64,
        num_actions: int = 6,
        lr: float = 0.0015,
        lr_min: float = 0.0002,
        lr_decay: float = 0.9995,
        gamma: float = 0.90,
        epsilon: float = 1.0,
        epsilon_min: float = 0.02,
        epsilon_decay: float = 0.995,
        batch_size: int = 64,
        buffer_capacity: int = 50000,
        target_sync_tau: float = 0.05,
        seed: int = 42,
    ) -> None:
        self.input_dim = input_dim
        self.hidden1 = hidden1
        self.hidden2 = hidden2
        self.num_actions = num_actions
        self.lr = lr
        self.lr_min = lr_min
        self.lr_decay = lr_decay
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.buffer_capacity = buffer_capacity
        self.target_sync_tau = target_sync_tau

        self.rng = np.random.default_rng(seed)
        self.online_params = self._init_weights()
        self.target_params = {k: v.copy() for k, v in self.online_params.items()}

        # Adam optimizer moments
        self.adam_m = {k: np.zeros_like(v) for k, v in self.online_params.items()}
        self.adam_v = {k: np.zeros_like(v) for k, v in self.online_params.items()}
        self.adam_t: int = 0

        # Compact circular Experience Replay arrays for fast mini-batch sampling
        self.buf_s = np.zeros((buffer_capacity, input_dim), dtype=np.float32)
        self.buf_a = np.zeros(buffer_capacity, dtype=np.int32)
        self.buf_r = np.zeros(buffer_capacity, dtype=np.float32)
        self.buf_ns = np.zeros((buffer_capacity, input_dim), dtype=np.float32)
        self.buf_done = np.zeros(buffer_capacity, dtype=np.float32)
        self.buf_nmask = np.ones((buffer_capacity, num_actions), dtype=bool)
        self.buf_ptr: int = 0
        self.buf_size: int = 0

        self.total_updates: int = 0
        self.episodes_trained: int = 0
        self.last_loss: float = 0.0

    def _init_weights(self) -> dict[str, np.ndarray]:
        w1 = self.rng.normal(
            0.0, np.sqrt(2.0 / self.input_dim), size=(self.input_dim, self.hidden1)
        ).astype(np.float32)
        b1 = np.zeros(self.hidden1, dtype=np.float32)

        w2 = self.rng.normal(
            0.0, np.sqrt(2.0 / self.hidden1), size=(self.hidden1, self.hidden2)
        ).astype(np.float32)
        b2 = np.zeros(self.hidden2, dtype=np.float32)

        # Dueling value & advantage heads
        wv = self.rng.normal(
            0.0, np.sqrt(1.0 / self.hidden2), size=(self.hidden2, 1)
        ).astype(np.float32)
        bv = np.zeros(1, dtype=np.float32)

        wa = self.rng.normal(
            0.0, np.sqrt(1.0 / self.hidden2), size=(self.hidden2, self.num_actions)
        ).astype(np.float32)
        ba = np.zeros(self.num_actions, dtype=np.float32)

        return {
            "w1": w1,
            "b1": b1,
            "w2": w2,
            "b2": b2,
            "wv": wv,
            "bv": bv,
            "wa": wa,
            "ba": ba,
        }

    @property
    def num_parameters(self) -> int:
        return sum(int(v.size) for v in self.online_params.values())

    def _forward(
        self, x: np.ndarray, params: dict[str, np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Forward pass for batch `x` of shape `(B, input_dim)`.
        Returns `(q_vals, z1, h1, z2, h2)`.
        """
        z1 = x @ params["w1"] + params["b1"]
        h1 = np.maximum(0.0, z1)
        z2 = h1 @ params["w2"] + params["b2"]
        h2 = np.maximum(0.0, z2)

        val = h2 @ params["wv"] + params["bv"]  # (B, 1)
        adv = h2 @ params["wa"] + params["ba"]  # (B, A)
        q_vals = val + (adv - np.mean(adv, axis=1, keepdims=True))
        return q_vals, z1, h1, z2, h2

    def predict_q(self, features: np.ndarray) -> np.ndarray:
        x = features[np.newaxis, :] if features.ndim == 1 else features
        q_vals, _, _, _, _ = self._forward(x, self.online_params)
        return q_vals[0] if features.ndim == 1 else q_vals

    def choose_action_from_features(
        self,
        features: np.ndarray,
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

        q_vals = self.predict_q(features)
        best_idx = max(valid_indices, key=lambda i: float(q_vals[i]))
        return ALL_ACTIONS[best_idx]

    def choose_action(
        self, gamestate: Gamestate, player_id: int, training: bool = False
    ) -> Action:
        features, action_mask, _ = extract_dqn_features_and_mask(gamestate, player_id)
        return self.choose_action_from_features(
            features, training=training, action_mask=action_mask
        )

    def store_transition(
        self,
        state: np.ndarray,
        action: Action,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        next_action_mask: list[bool] | None = None,
    ) -> None:
        idx = self.buf_ptr
        self.buf_s[idx] = state
        self.buf_a[idx] = ALL_ACTIONS.index(action)
        # Scale rewards by 0.05 for well-conditioned neural network gradients
        self.buf_r[idx] = reward * 0.05
        self.buf_ns[idx] = next_state
        self.buf_done[idx] = 1.0 if done else 0.0
        if next_action_mask is not None and any(next_action_mask):
            self.buf_nmask[idx] = np.array(next_action_mask, dtype=bool)
        else:
            self.buf_nmask[idx] = True

        self.buf_ptr = (self.buf_ptr + 1) % self.buffer_capacity
        self.buf_size = min(self.buf_size + 1, self.buffer_capacity)

    def train_step(self) -> float:
        """
        Samples a mini-batch from the Experience Replay Buffer and performs
        one Double-DQN gradient descent step with masked target Q-values:
            a* = argmax_{a' in A_non_suicidal(s')} Q_online(s', a')
            y  = r + (1 - done) * gamma * Q_target(s', a*)
        """
        if self.buf_size < self.batch_size:
            return 0.0

        indices = self.rng.integers(0, self.buf_size, size=self.batch_size)
        s_batch = self.buf_s[indices]
        a_batch = self.buf_a[indices]
        r_batch = self.buf_r[indices]
        ns_batch = self.buf_ns[indices]
        done_batch = self.buf_done[indices]
        nmask_batch = self.buf_nmask[indices]

        # 1. Compute Double-DQN target with action masking
        next_q_online, _, _, _, _ = self._forward(ns_batch, self.online_params)
        masked_next_q_online = np.where(nmask_batch, next_q_online, -1e9)
        best_next_actions = np.argmax(masked_next_q_online, axis=1)

        next_q_target, _, _, _, _ = self._forward(ns_batch, self.target_params)
        batch_rows = np.arange(self.batch_size)
        max_next_q = next_q_target[batch_rows, best_next_actions]
        targets = r_batch + (1.0 - done_batch) * self.gamma * max_next_q

        # 2. Forward pass on online network
        q_pred, z1, h1, z2, h2 = self._forward(s_batch, self.online_params)
        pred_chosen = q_pred[batch_rows, a_batch]

        # Huber (smooth L1) loss gradient on TD error
        td_diff = pred_chosen - targets
        loss = float(np.mean(np.where(np.abs(td_diff) < 1.0, 0.5 * td_diff**2, np.abs(td_diff) - 0.5)))
        self.last_loss = loss

        grad_chosen = np.clip(td_diff, -1.0, 1.0) / float(self.batch_size)
        dq = np.zeros_like(q_pred)
        dq[batch_rows, a_batch] = grad_chosen

        # 3. Backpropagation through Dueling heads (V and A)
        # Q = V + (A - mean(A))
        dval = np.sum(dq, axis=1, keepdims=True)  # (B, 1)
        dadv = dq - np.mean(dq, axis=1, keepdims=True)  # (B, A)

        grads: dict[str, np.ndarray] = {}
        grads["wv"] = h2.T @ dval
        grads["bv"] = np.sum(dval, axis=0)
        grads["wa"] = h2.T @ dadv
        grads["ba"] = np.sum(dadv, axis=0)

        dh2 = dval @ self.online_params["wv"].T + dadv @ self.online_params["wa"].T
        dz2 = dh2 * (z2 > 0.0)
        grads["w2"] = h1.T @ dz2
        grads["b2"] = np.sum(dz2, axis=0)

        dh1 = dz2 @ self.online_params["w2"].T
        dz1 = dh1 * (z1 > 0.0)
        grads["w1"] = s_batch.T @ dz1
        grads["b1"] = np.sum(dz1, axis=0)

        # 4. Adam parameter update + Polyak target network soft update
        self.adam_t += 1
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        bias_corr1 = 1.0 - beta1**self.adam_t
        bias_corr2 = 1.0 - beta2**self.adam_t

        for k, p in self.online_params.items():
            g = grads[k]
            self.adam_m[k] = beta1 * self.adam_m[k] + (1.0 - beta1) * g
            self.adam_v[k] = beta2 * self.adam_v[k] + (1.0 - beta2) * (g * g)
            m_hat = self.adam_m[k] / bias_corr1
            v_hat = self.adam_v[k] / bias_corr2
            p -= self.lr * m_hat / (np.sqrt(v_hat) + eps)

            # Soft update target network
            self.target_params[k] = (
                (1.0 - self.target_sync_tau) * self.target_params[k]
                + self.target_sync_tau * p
            )

        self.total_updates += 1
        return loss

    def decay_epsilon(self) -> None:
        self.episodes_trained += 1
        if self.epsilon > self.epsilon_min:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        if self.lr > self.lr_min:
            self.lr = max(self.lr_min, self.lr * self.lr_decay)

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        payload = {
            "online_params": self.online_params,
            "target_params": self.target_params,
            "lr": self.lr,
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
        self.online_params = payload["online_params"]
        self.target_params = payload["target_params"]
        self.lr = payload.get("lr", self.lr)
        self.gamma = payload.get("gamma", self.gamma)
        self.epsilon = payload.get("epsilon", self.epsilon_min)
        self.total_updates = payload.get("total_updates", 0)
        self.episodes_trained = payload.get("episodes_trained", 0)
        return True
