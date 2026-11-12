from __future__ import annotations

import argparse

from agents.dqn import DQNAgent
from agents.qlearning import QLearningAgent
from core.commands.gamerules import create_initial_gamestate
from core.entities.player import Player
from core.gateways.gamemaster import GameMaster, TrainingSummary
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position

DEFAULT_QTABLE_PATH = "./agents/qtable.pkl"
DEFAULT_DQN_PATH = "./agents/dqn_model.pkl"


def gen_gamestate() -> Gamestate:
    return create_initial_gamestate(width=9, height=9)


def gen_players() -> list[Player]:
    return [
        Player(0, Position(0, 0), Direction.DOWN),
        Player(1, Position(8, 0), Direction.DOWN),
        Player(2, Position(0, 8), Direction.UP),
        Player(3, Position(8, 8), Direction.UP),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DynamiteMan - Bomberman PvP & Reinforcement Learning (DQN / Tabular Q-Learning) Prototype"
    )
    parser.add_argument(
        "--agent",
        choices=["dqn", "qlearn", "compare"],
        default="dqn",
        help="RL agent architecture: 'dqn' (Deep Q-Network), 'qlearn' (Tabular Q-Learning), or 'compare' (2 DQN vs 2 Q-Learn)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=450,
        help="Number of headless 4-player training episodes (default: 450)",
    )
    parser.add_argument(
        "--eval-interval",
        type=int,
        default=150,
        help="Evaluate RL agent every N episodes during training (default: 150)",
    )
    parser.add_argument(
        "--headless-only",
        action="store_true",
        help="Run headless training and benchmarks only, without opening Pygame window",
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        help="Skip training and load existing model from ./agents/dqn_model.pkl or ./agents/qtable.pkl",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Start the visual arena in Human (P1) vs 3 AIs mode (can also toggle with [M])",
    )
    parser.add_argument(
        "--tps",
        type=int,
        default=4,
        help="Visual game logic ticks per second (default: 4, so 240 ticks = 60s)",
    )
    return parser.parse_args()


def _prepare_qlearn(
    gm: GameMaster, args: argparse.Namespace
) -> tuple[QLearningAgent, TrainingSummary]:
    q_agent = QLearningAgent(
        alpha=0.15,
        gamma=0.92,
        epsilon=1.0,
        epsilon_min=0.02,
        epsilon_decay=0.996,
    )
    if args.load_only and q_agent.load(DEFAULT_QTABLE_PATH):
        print(
            f"Loaded existing Tabular Q-table from {DEFAULT_QTABLE_PATH} "
            f"({len(q_agent.q_table)} states, {q_agent.episodes_trained} episodes)."
        )
        wr_hum, _, _, _ = gm.evaluate_agent(
            q_agent, opponent_type="human_like", num_matches=40
        )
        summary = TrainingSummary(
            agent_type="Tabular Q-Learning",
            total_episodes=q_agent.episodes_trained,
            q_states_learned=len(q_agent.q_table),
            final_win_rate_vs_human_like=wr_hum,
        )
    else:
        summary = gm.train_headless(
            agent=q_agent,
            num_episodes=args.episodes,
            eval_interval=args.eval_interval,
            eval_matches=60,
            save_path=DEFAULT_QTABLE_PATH,
            verbose=True,
        )
    return q_agent, summary


def _prepare_dqn(
    gm: GameMaster, args: argparse.Namespace
) -> tuple[DQNAgent, TrainingSummary]:
    dqn_agent = DQNAgent(
        lr=0.0015,
        gamma=0.90,
        epsilon=1.0,
        epsilon_min=0.02,
        epsilon_decay=0.994,
    )
    if args.load_only and dqn_agent.load(DEFAULT_DQN_PATH):
        print(
            f"Loaded existing Deep Q-Network from {DEFAULT_DQN_PATH} "
            f"({dqn_agent.num_parameters:,} params, {dqn_agent.episodes_trained} episodes)."
        )
        wr_hum, _, _, _ = gm.evaluate_agent(
            dqn_agent, opponent_type="human_like", num_matches=40
        )
        summary = TrainingSummary(
            agent_type="Deep Q-Network (DQN)",
            total_episodes=dqn_agent.episodes_trained,
            q_states_learned=dqn_agent.total_updates,
            final_win_rate_vs_human_like=wr_hum,
        )
    else:
        summary = gm.train_dqn_headless(
            agent=dqn_agent,
            num_episodes=args.episodes,
            eval_interval=args.eval_interval,
            eval_matches=60,
            save_path=DEFAULT_DQN_PATH,
            verbose=True,
        )
    return dqn_agent, summary


def main() -> None:
    args = parse_args()
    gm = GameMaster(width=9, height=9, scale=64)

    secondary_agent: QLearningAgent | DQNAgent | None = None
    if args.agent == "qlearn":
        primary_agent, summary = _prepare_qlearn(gm, args)
    elif args.agent == "compare":
        primary_agent, summary = _prepare_dqn(gm, args)
        q_agent = QLearningAgent()
        if not q_agent.load(DEFAULT_QTABLE_PATH):
            q_agent, _ = _prepare_qlearn(gm, args)
        secondary_agent = q_agent
    else:
        primary_agent, summary = _prepare_dqn(gm, args)

    if not args.headless_only:
        print("\nLaunching Pygame window to watch the 4 trained AI players battle...")
        print(
            "Tip: Press [M] in the window to play as Human (P1) against 3 RL AIs!"
        )
        gm.run_visual_arena(
            agent=primary_agent,
            summary=summary,
            initial_human_mode=args.human,
            ticks_per_second=args.tps,
            secondary_agent=secondary_agent,
        )


if __name__ == "__main__":
    main()
