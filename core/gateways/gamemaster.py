from __future__ import annotations

from dataclasses import dataclass, field
import sys
import time

import numpy as np
import pygame

from agents.dqn import (
    DQNAgent,
    compute_dqn_reward,
    extract_dqn_features_and_mask,
)
from agents.qlearning import (
    HeuristicHumanLikeAgent,
    QLearningAgent,
    RandomAgent,
    StateTuple,
    compute_reward,
    extract_state_and_mask,
)
from core.commands.gamerules import create_initial_gamestate, step_gamestate
from core.controllers.ai import AI, AgentProtocol
from core.controllers.human import Human
from core.gateways.graphic import Graphic
from core.ports.controller import Controller
from core.vos.action import Action
from core.vos.gamestate import Gamestate


@dataclass
class EvalSnapshot:
    episode: int
    elapsed_sec: float
    epsilon: float
    q_states: int
    win_rate_vs_random: float
    win_rate_vs_human_like: float
    suicide_rate: float
    avg_kills: float
    avg_boxes: float


@dataclass
class TrainingSummary:
    agent_type: str = "Tabular Q-Learning"
    total_episodes: int = 0
    total_ticks: int = 0
    elapsed_sec: float = 0.0
    q_states_learned: int = 0
    final_win_rate_vs_random: float = 0.0
    final_win_rate_vs_human_like: float = 0.0
    competent_milestone_ep: int | None = None
    competent_milestone_sec: float | None = None
    human_parity_milestone_ep: int | None = None
    human_parity_milestone_sec: float | None = None
    superhuman_milestone_ep: int | None = None
    superhuman_milestone_sec: float | None = None
    history: list[EvalSnapshot] = field(default_factory=list)


class GameMaster:
    """
    Coordinates headless RL training (both Tabular Q-Learning and Deep Q-Network),
    benchmarking, and the Pygame visual showcase (4 AI Battle, 2 DQN vs 2 Q-Learn,
    and Human vs 3 AI PvP).
    """

    def __init__(
        self,
        width: int = 9,
        height: int = 9,
        scale: int = 64,
    ) -> None:
        self.width = width
        self.height = height
        self.scale = scale

    def evaluate_agent(
        self,
        rl_agent: AgentProtocol,
        opponent_type: str = "human_like",
        num_matches: int = 60,
        custom_opponent: AgentProtocol | None = None,
    ) -> tuple[float, float, float, float]:
        """
        Runs `num_matches` headless 4-player games where 1 player is `rl_agent`
        (rotated across all 4 spawn corners for fairness) and the other 3 players
        are `HeuristicHumanLikeAgent`, `RandomAgent`, or `custom_opponent`.

        Returns (win_rate_pct, suicide_rate_pct, avg_kills, avg_boxes).
        """
        wins = 0
        suicides = 0
        total_kills = 0
        total_boxes = 0

        for match_idx in range(num_matches):
            q_slot = match_idx % 4
            controllers: list[Controller] = []
            for slot in range(4):
                if slot == q_slot:
                    controllers.append(AI(rl_agent, training=False))
                elif custom_opponent is not None:
                    controllers.append(AI(custom_opponent, training=False))
                elif opponent_type == "random":
                    controllers.append(AI(RandomAgent(), training=False))
                else:
                    controllers.append(AI(HeuristicHumanLikeAgent(), training=False))

            gs = create_initial_gamestate(
                width=self.width,
                height=self.height,
                controllers=controllers,
            )

            q_suicided = False
            while not gs.is_over:
                actions_by_player: dict[int, list[Action]] = {}
                for p in gs.players:
                    if p.alive and p.controller is not None:
                        actions_by_player[p.id] = p.controller.get_actions(gs, p.id)
                events = step_gamestate(gs, actions_by_player)
                if events[q_slot].suicided:
                    q_suicided = True

            if gs.winner_id == q_slot:
                wins += 1
            if q_suicided:
                suicides += 1
            total_kills += gs.players[q_slot].kills
            total_boxes += gs.players[q_slot].boxes_destroyed

        win_rate = (wins / num_matches) * 100.0
        suicide_rate = (suicides / num_matches) * 100.0
        avg_kills = total_kills / num_matches
        avg_boxes = total_boxes / num_matches
        return win_rate, suicide_rate, avg_kills, avg_boxes

    def train_headless(
        self,
        agent: QLearningAgent,
        num_episodes: int = 1500,
        eval_interval: int = 250,
        eval_matches: int = 60,
        save_path: str = "./agents/qtable.pkl",
        verbose: bool = True,
    ) -> TrainingSummary:
        """
        Trains the shared Tabular Q-Learning agent via 4-player self-play in a
        non-graphical environment with unlimited tick rate.
        """
        summary = TrainingSummary(agent_type="Tabular Q-Learning")
        start_time = time.perf_counter()

        if verbose:
            print("=" * 82)
            print(" DYNAMITEMAN - HEADLESS TABULAR Q-LEARNING SELF-PLAY TRAINING")
            print("=" * 82)
            print(
                f" Arena: {self.width}x{self.height} | Players: 4 (Shared Q-Table) | "
                f"Episodes: {num_episodes}"
            )
            print(
                " Note: In 4-player Free-For-All, equal skill vs 3 opponents = 25% Win Rate."
            )
            print("-" * 82)
            print(
                f"{'Ep':>6} | {'Time(s)':>7} | {'Eps':>5} | {'States':>6} | "
                f"{'WR vs Rand':>10} | {'WR vs HumanBot':>14} | {'Suicide%':>8} | {'Kills/G':>7}"
            )
            print("-" * 82)

        def record_eval(ep: int) -> None:
            elapsed = time.perf_counter() - start_time
            wr_rand, _, _, _ = self.evaluate_agent(
                agent, opponent_type="random", num_matches=eval_matches
            )
            wr_hum, suic_rate, avg_k, avg_b = self.evaluate_agent(
                agent, opponent_type="human_like", num_matches=eval_matches
            )
            snap = EvalSnapshot(
                episode=ep,
                elapsed_sec=elapsed,
                epsilon=agent.epsilon,
                q_states=len(agent.q_table),
                win_rate_vs_random=wr_rand,
                win_rate_vs_human_like=wr_hum,
                suicide_rate=suic_rate,
                avg_kills=avg_k,
                avg_boxes=avg_b,
            )
            summary.history.append(snap)
            summary.final_win_rate_vs_random = wr_rand
            summary.final_win_rate_vs_human_like = wr_hum

            if (
                summary.competent_milestone_ep is None
                and wr_rand >= 70.0
                and suic_rate <= 12.0
            ):
                summary.competent_milestone_ep = ep
                summary.competent_milestone_sec = elapsed

            if summary.human_parity_milestone_ep is None and wr_hum >= 30.0:
                summary.human_parity_milestone_ep = ep
                summary.human_parity_milestone_sec = elapsed

            if summary.superhuman_milestone_ep is None and wr_hum >= 55.0:
                summary.superhuman_milestone_ep = ep
                summary.superhuman_milestone_sec = elapsed

            if verbose:
                print(
                    f"{ep:6d} | {elapsed:7.2f} | {agent.epsilon:5.2f} | "
                    f"{len(agent.q_table):6d} | {wr_rand:9.1f}% | "
                    f"{wr_hum:13.1f}% | {suic_rate:7.1f}% | {avg_k:7.2f}"
                )

        if agent.episodes_trained == 0:
            record_eval(0)

        for ep in range(1, num_episodes + 1):
            gs = create_initial_gamestate(width=self.width, height=self.height)
            cached_state_mask: dict[int, tuple[StateTuple, list[bool]]] = {
                p.id: extract_state_and_mask(gs, p.id) for p in gs.players if p.alive
            }

            while not gs.is_over:
                prev_states: dict[int, StateTuple] = {}
                chosen_actions: dict[int, Action] = {}
                actions_payload: dict[int, list[Action]] = {}

                for p in gs.players:
                    if not p.alive:
                        continue
                    st, mask = cached_state_mask[p.id]
                    act = agent.choose_action_from_state(
                        st, training=True, action_mask=mask
                    )
                    prev_states[p.id] = st
                    chosen_actions[p.id] = act
                    actions_payload[p.id] = [act]

                events = step_gamestate(gs, actions_payload)
                summary.total_ticks += 1
                next_cache: dict[int, tuple[StateTuple, list[bool]]] = {}

                for pid, prev_st in prev_states.items():
                    act = chosen_actions[pid]
                    ev = events[pid]
                    done = ev.died or gs.is_over
                    if done:
                        next_st: StateTuple = (0, 0, 0, 0, 0, 0)
                        next_mask: list[bool] = [False, False, False, False, False, True]
                    else:
                        next_st, next_mask = extract_state_and_mask(gs, pid)
                        next_cache[pid] = (next_st, next_mask)
                    reward = compute_reward(ev, prev_st, act, next_st)
                    agent.update(
                        prev_st,
                        act,
                        reward,
                        next_st,
                        done,
                        next_action_mask=next_mask,
                    )

                cached_state_mask = next_cache

            agent.decay_epsilon()

            if ep % eval_interval == 0 or ep == num_episodes:
                record_eval(agent.episodes_trained)

        summary.total_episodes = agent.episodes_trained
        summary.elapsed_sec = time.perf_counter() - start_time
        summary.q_states_learned = len(agent.q_table)

        if save_path:
            agent.save(save_path)

        if verbose:
            self.print_training_report(summary, save_path)

        return summary

    def train_dqn_headless(
        self,
        agent: DQNAgent,
        num_episodes: int = 450,
        eval_interval: int = 150,
        eval_matches: int = 60,
        save_path: str = "./agents/dqn_model.pkl",
        verbose: bool = True,
    ) -> TrainingSummary:
        """
        Trains the Deep Q-Network (Dueling Double-DQN) agent via 4-player self-play
        using raw 9x9 multi-channel grid features, Experience Replay, and Temporal A*
        Suicide-Safety Action Masking (`UNSAFE != SUICIDAL`).
        """
        summary = TrainingSummary(agent_type="Deep Q-Network (DQN)")
        start_time = time.perf_counter()

        if verbose:
            print("=" * 86)
            print(" DYNAMITEMAN - HEADLESS DEEP REINFORCEMENT LEARNING (DUELING DOUBLE-DQN) TRAINING")
            print("=" * 86)
            print(
                f" Arena: {self.width}x{self.height} | Input: 508 Features (9x9 Grid + 5x5 Patch + Rays) | "
                f"Params: {agent.num_parameters:,}"
            )
            print(
                " Action Masking: Temporal A* Suicide-Safety (UNSAFE != SUICIDAL: unsafe stays unmasked!)"
            )
            print("-" * 86)
            print(
                f"{'Ep':>6} | {'Time(s)':>7} | {'Eps':>5} | {'GradSteps':>9} | "
                f"{'WR vs Rand':>10} | {'WR vs HumanBot':>14} | {'Suicide%':>8} | {'Kills/G':>7}"
            )
            print("-" * 86)

        best_score: float = -1.0
        best_online: dict[str, np.ndarray] | None = None
        best_target: dict[str, np.ndarray] | None = None
        best_wr_hum: float = 0.0
        best_wr_rand: float = 0.0

        def record_eval(ep: int) -> None:
            nonlocal best_score, best_online, best_target, best_wr_hum, best_wr_rand
            elapsed = time.perf_counter() - start_time
            wr_rand, _, _, _ = self.evaluate_agent(
                agent, opponent_type="random", num_matches=eval_matches
            )
            wr_hum, suic_rate, avg_k, avg_b = self.evaluate_agent(
                agent, opponent_type="human_like", num_matches=eval_matches
            )
            snap = EvalSnapshot(
                episode=ep,
                elapsed_sec=elapsed,
                epsilon=agent.epsilon,
                q_states=agent.total_updates,
                win_rate_vs_random=wr_rand,
                win_rate_vs_human_like=wr_hum,
                suicide_rate=suic_rate,
                avg_kills=avg_k,
                avg_boxes=avg_b,
            )
            summary.history.append(snap)
            summary.final_win_rate_vs_random = wr_rand
            summary.final_win_rate_vs_human_like = wr_hum

            score = wr_hum + 0.25 * wr_rand + 5.0 * avg_k
            if ep > 0 and score >= best_score:
                best_score = score
                best_wr_hum = wr_hum
                best_wr_rand = wr_rand
                best_online = {k: v.copy() for k, v in agent.online_params.items()}
                best_target = {k: v.copy() for k, v in agent.target_params.items()}

            if (
                summary.competent_milestone_ep is None
                and wr_rand >= 70.0
                and suic_rate <= 12.0
            ):
                summary.competent_milestone_ep = ep
                summary.competent_milestone_sec = elapsed

            if summary.human_parity_milestone_ep is None and wr_hum >= 30.0:
                summary.human_parity_milestone_ep = ep
                summary.human_parity_milestone_sec = elapsed

            if summary.superhuman_milestone_ep is None and wr_hum >= 55.0:
                summary.superhuman_milestone_ep = ep
                summary.superhuman_milestone_sec = elapsed

            if verbose:
                print(
                    f"{ep:6d} | {elapsed:7.2f} | {agent.epsilon:5.2f} | "
                    f"{agent.total_updates:9d} | {wr_rand:9.1f}% | "
                    f"{wr_hum:13.1f}% | {suic_rate:7.1f}% | {avg_k:7.2f}"
                )

        if agent.episodes_trained == 0:
            record_eval(0)

        zero_feat = np.zeros(agent.input_dim, dtype=np.float32)
        zero_aux = {"in_danger": 0.0, "ticks_to_safe": 0.0, "bomb_opp": 0.0, "potential": 0.0}

        for ep in range(1, num_episodes + 1):
            gs = create_initial_gamestate(width=self.width, height=self.height)
            cached_obs: dict[int, tuple[np.ndarray, list[bool], dict[str, float]]] = {
                p.id: extract_dqn_features_and_mask(gs, p.id)
                for p in gs.players
                if p.alive
            }

            step_count = 0
            while not gs.is_over:
                prev_obs: dict[int, tuple[np.ndarray, list[bool], dict[str, float]]] = {}
                chosen_actions: dict[int, Action] = {}
                actions_payload: dict[int, list[Action]] = {}

                for p in gs.players:
                    if not p.alive:
                        continue
                    feat, mask, aux = cached_obs[p.id]
                    act = agent.choose_action_from_features(
                        feat, training=True, action_mask=mask
                    )
                    prev_obs[p.id] = (feat, mask, aux)
                    chosen_actions[p.id] = act
                    actions_payload[p.id] = [act]

                events = step_gamestate(gs, actions_payload)
                summary.total_ticks += 1
                step_count += 1
                next_cache: dict[int, tuple[np.ndarray, list[bool], dict[str, float]]] = {}

                for pid, (prev_feat, _, prev_aux) in prev_obs.items():
                    act = chosen_actions[pid]
                    ev = events[pid]
                    done = ev.died or gs.is_over
                    if done:
                        next_feat = zero_feat
                        next_mask = [False, False, False, False, False, True]
                        next_aux = zero_aux
                    else:
                        next_feat, next_mask, next_aux = extract_dqn_features_and_mask(
                            gs, pid
                        )
                        next_cache[pid] = (next_feat, next_mask, next_aux)

                    reward = compute_dqn_reward(ev, prev_aux, act, next_aux)
                    agent.store_transition(
                        prev_feat,
                        act,
                        reward,
                        next_feat,
                        done,
                        next_action_mask=next_mask,
                    )

                cached_obs = next_cache
                # Run mini-batch neural network gradient update every 2 ticks
                if step_count % 2 == 0:
                    agent.train_step()

            agent.decay_epsilon()

            if ep % eval_interval == 0 or ep == num_episodes:
                record_eval(agent.episodes_trained)

        if best_online is not None and best_target is not None:
            agent.online_params = best_online
            agent.target_params = best_target
            summary.final_win_rate_vs_human_like = best_wr_hum
            summary.final_win_rate_vs_random = best_wr_rand

        summary.total_episodes = agent.episodes_trained
        summary.elapsed_sec = time.perf_counter() - start_time
        summary.q_states_learned = agent.total_updates

        if save_path:
            agent.save(save_path)

        if verbose:
            self.print_training_report(summary, save_path)

        return summary

    def print_training_report(
        self, summary: TrainingSummary, save_path: str
    ) -> None:
        print("=" * 86)
        print(f" {summary.agent_type.upper()} BENCHMARK REPORT (HOW FAST DOES IT LEARN?)")
        print("=" * 86)
        ticks_per_sec = summary.total_ticks / max(0.001, summary.elapsed_sec)
        eps_per_sec = summary.total_episodes / max(0.001, summary.elapsed_sec)
        print(
            f" * Total Training Time : {summary.elapsed_sec:.2f}s "
            f"({summary.total_episodes} episodes, {summary.total_ticks} ticks)"
        )
        print(
            f" * Simulation Speed    : {ticks_per_sec:,.0f} ticks/sec "
            f"({eps_per_sec:.1f} matches/sec)"
        )
        if "DQN" in summary.agent_type:
            print(
                f" * Neural Net Updates  : {summary.q_states_learned:,} mini-batch gradient steps "
                f"(saved to {save_path})"
            )
        else:
            print(
                f" * Learned Q-Table     : {summary.q_states_learned} unique states "
                f"x 6 actions (saved to {save_path})"
            )
        print("-" * 86)
        if summary.competent_milestone_ep is not None:
            print(
                f" [1] Safe & Competent Play (>70% WR vs Random, low suicide): "
                f"~{summary.competent_milestone_ep} episodes ({summary.competent_milestone_sec:.2f}s)"
            )
        if summary.human_parity_milestone_ep is not None:
            print(
                f" [2] Human-Parity Play     (>=30% WR vs 3 Human-like bots): "
                f"~{summary.human_parity_milestone_ep} episodes ({summary.human_parity_milestone_sec:.2f}s)"
            )
        if summary.superhuman_milestone_ep is not None:
            print(
                f" [3] Better Than Human     (>=55% WR vs 3 Human-like bots): "
                f"~{summary.superhuman_milestone_ep} episodes ({summary.superhuman_milestone_sec:.2f}s)"
            )
        print(
            f" * Final Evaluation    : {summary.final_win_rate_vs_random:.1f}% WR vs Random | "
            f"{summary.final_win_rate_vs_human_like:.1f}% WR vs 3 Human-like Bots (25% = par)"
        )
        print("=" * 86)

    def run_visual_arena(
        self,
        agent: QLearningAgent | DQNAgent,
        summary: TrainingSummary,
        initial_human_mode: bool = False,
        ticks_per_second: int = 4,
        secondary_agent: QLearningAgent | DQNAgent | None = None,
    ) -> None:
        """
        Opens the Pygame window and runs the visual battle between the 4 trained
        RL AI players (or 2 DQN vs 2 Tabular Q-Learning AIs if `secondary_agent`
        is provided), with hotkeys to toggle Human vs 3 AI PvP, adjust speed,
        restart rounds, or run extra training.
        """
        pygame.init()
        human_mode = initial_human_mode
        human_ctrl = Human()
        session_wins: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
        round_num = 1
        tps = ticks_per_second

        is_dqn = isinstance(agent, DQNAgent)
        compare_mode = secondary_agent is not None

        def get_role_labels() -> dict[int, str]:
            labels: dict[int, str] = {}
            for i in range(4):
                if compare_mode:
                    labels[i] = "DQN AI" if i in (0, 2) else "Q-Learn AI"
                else:
                    labels[i] = "DQN AI" if is_dqn else "Q-Agent AI"
            return labels

        def build_controllers() -> list[Controller]:
            ctrls: list[Controller] = []
            for i in range(4):
                if human_mode and i == 0:
                    ctrls.append(human_ctrl)
                elif compare_mode and secondary_agent is not None:
                    chosen = agent if i in (0, 2) else secondary_agent
                    ctrls.append(AI(chosen, training=False))
                else:
                    ctrls.append(AI(agent, training=False))
            return ctrls

        gs = create_initial_gamestate(
            width=self.width,
            height=self.height,
            controllers=build_controllers(),
        )
        ge = Graphic(self.scale, gs.width, gs.height, gs.players)
        clock = pygame.time.Clock()

        fps = 60
        frame_accum = 0.0
        post_match_wait_frames = 0

        while True:
            frames_per_tick = max(1.0, fps / float(tps))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if human_mode:
                    human_ctrl.record_event(event)
                    if (
                        event.type == pygame.KEYDOWN
                        and gs.players
                        and gs.players[0].alive
                    ):
                        from core.vos.direction import Direction
                        if event.key in (pygame.K_UP, pygame.K_w):
                            gs.players[0].facing = Direction.UP
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            gs.players[0].facing = Direction.DOWN
                        elif event.key in (pygame.K_LEFT, pygame.K_a):
                            gs.players[0].facing = Direction.LEFT
                        elif event.key in (pygame.K_RIGHT, pygame.K_d):
                            gs.players[0].facing = Direction.RIGHT

                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        pygame.quit()
                        sys.exit()
                    elif event.key == pygame.K_m:
                        human_mode = not human_mode
                        round_num += 1
                        gs = create_initial_gamestate(
                            width=self.width,
                            height=self.height,
                            controllers=build_controllers(),
                        )
                        post_match_wait_frames = 0
                    elif event.key == pygame.K_r:
                        round_num += 1
                        gs = create_initial_gamestate(
                            width=self.width,
                            height=self.height,
                            controllers=build_controllers(),
                        )
                        post_match_wait_frames = 0
                    elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        tps = min(30, tps + 2)
                    elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        tps = max(2, tps - 2)
                    elif event.key == pygame.K_t:
                        if isinstance(agent, DQNAgent):
                            extra = self.train_dqn_headless(
                                agent,
                                num_episodes=200,
                                eval_interval=100,
                                eval_matches=40,
                                verbose=True,
                            )
                            summary.q_states_learned = agent.total_updates
                        else:
                            extra = self.train_headless(
                                agent,
                                num_episodes=200,
                                eval_interval=100,
                                eval_matches=40,
                                verbose=True,
                            )
                            summary.q_states_learned = len(agent.q_table)
                        summary.total_episodes = agent.episodes_trained
                        summary.elapsed_sec += extra.elapsed_sec
                        summary.final_win_rate_vs_human_like = (
                            extra.final_win_rate_vs_human_like
                        )

            if not gs.is_over:
                frame_accum += 1.0
                if frame_accum >= frames_per_tick:
                    frame_accum -= frames_per_tick
                    actions_by_player: dict[int, list[Action]] = {}
                    for p in gs.players:
                        if p.alive and p.controller is not None:
                            actions_by_player[p.id] = p.controller.get_actions(
                                gs, p.id
                            )
                    step_gamestate(gs, actions_by_player)
                    if gs.is_over and gs.winner_id is not None:
                        session_wins[gs.winner_id] = (
                            session_wins.get(gs.winner_id, 0) + 1
                        )
            else:
                post_match_wait_frames += 1
                if post_match_wait_frames >= int(fps * 2.5):
                    round_num += 1
                    gs = create_initial_gamestate(
                        width=self.width,
                        height=self.height,
                        controllers=build_controllers(),
                    )
                    post_match_wait_frames = 0
                    frame_accum = 0.0

            sub_ratio = min(0.99, frame_accum / max(1.0, frames_per_tick))
            if compare_mode:
                mode_label = (
                    "Human vs DQN & Q-Learn"
                    if human_mode
                    else "2 DQN vs 2 Q-Learn Battle"
                )
                agent_title = "Deep DQN vs Tabular Q-Learn"
                stat_label = f"DQN Params: {agent.num_parameters:,}" if isinstance(agent, DQNAgent) else f"States: {summary.q_states_learned}"
            elif is_dqn and isinstance(agent, DQNAgent):
                mode_label = (
                    "Human (P1) vs 3 DQN AIs"
                    if human_mode
                    else "4 Deep RL (DQN) Battle"
                )
                agent_title = "Deep Q-Network (Dueling DQN)"
                stat_label = f"Params: {agent.num_parameters:,} | Upd: {agent.total_updates:,}"
            else:
                mode_label = (
                    "Human (P1) vs 3 AIs"
                    if human_mode
                    else "4 Trained AIs Battle"
                )
                agent_title = "Tabular Q-Learning Agent"
                stat_label = f"Learned States: {summary.q_states_learned}"

            hud_info = {
                "mode": mode_label,
                "agent_title": agent_title,
                "stat_label": stat_label,
                "round": round_num,
                "tps": tps,
                "episodes": agent.episodes_trained,
                "q_states": summary.q_states_learned,
                "train_time_s": summary.elapsed_sec,
                "vs_human_wr": summary.final_win_rate_vs_human_like,
                "wins": session_wins,
                "human_id": 0 if human_mode else None,
                "role_labels": get_role_labels(),
            }

            ge.draw(gs, sub_frame_ratio=sub_ratio, hud_info=hud_info)
            clock.tick(fps)
