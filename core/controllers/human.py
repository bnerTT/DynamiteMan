from __future__ import annotations

from collections import deque

import pygame

from core.ports.controller import Controller
from core.vos.action import Action
from core.vos.gamestate import Gamestate

_KEY_TO_MOVE: dict[int, Action] = {
    pygame.K_UP: Action.UP,
    pygame.K_w: Action.UP,
    pygame.K_DOWN: Action.DOWN,
    pygame.K_s: Action.DOWN,
    pygame.K_LEFT: Action.LEFT,
    pygame.K_a: Action.LEFT,
    pygame.K_RIGHT: Action.RIGHT,
    pygame.K_d: Action.RIGHT,
}


class Human(Controller):
    """
    Responsive Human controller with:
      - 2-step corner-turn input queue (`_move_queue`) so rapid two-key sequences
        (e.g. RIGHT -> DOWN around a pillar) are never dropped between ticks,
      - Most-recently-pressed held-key priority (`_held_dirs`) so diagonal key
        rollovers immediately switch to the newest direction,
      - Single-press bomb buffering on KEYDOWN (`SPACE` or `ENTER`).
    """

    def __init__(self) -> None:
        self._move_queue: deque[Action] = deque(maxlen=2)
        self._held_dirs: list[Action] = []
        self._buffered_bomb: bool = False

    def record_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in _KEY_TO_MOVE:
                act = _KEY_TO_MOVE[event.key]
                if not self._move_queue or self._move_queue[-1] != act:
                    self._move_queue.append(act)
                if act in self._held_dirs:
                    self._held_dirs.remove(act)
                self._held_dirs.append(act)
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._buffered_bomb = True
        elif event.type == pygame.KEYUP:
            if event.key in _KEY_TO_MOVE:
                act = _KEY_TO_MOVE[event.key]
                if act in self._held_dirs:
                    self._held_dirs.remove(act)

    def get_actions(self, state: Gamestate, player_id: int) -> list[Action]:
        actions: list[Action] = []
        keys = pygame.key.get_pressed()

        # Sync _held_dirs with actual pressed state in case window lost focus
        still_held: list[Action] = []
        for act in self._held_dirs:
            if (
                (act == Action.UP and (keys[pygame.K_UP] or keys[pygame.K_w]))
                or (act == Action.DOWN and (keys[pygame.K_DOWN] or keys[pygame.K_s]))
                or (act == Action.LEFT and (keys[pygame.K_LEFT] or keys[pygame.K_a]))
                or (act == Action.RIGHT and (keys[pygame.K_RIGHT] or keys[pygame.K_d]))
            ):
                still_held.append(act)
        self._held_dirs = still_held

        move_act: Action | None = None
        if self._move_queue:
            move_act = self._move_queue.popleft()
        elif self._held_dirs:
            # Prefer the most recently pressed direction that is still held down
            move_act = self._held_dirs[-1]
        else:
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                move_act = Action.UP
            elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
                move_act = Action.DOWN
            elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
                move_act = Action.LEFT
            elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                move_act = Action.RIGHT

        if move_act is not None:
            actions.append(move_act)

        if self._buffered_bomb:
            actions.append(Action.BOMB)
            self._buffered_bomb = False

        if not actions:
            actions.append(Action.IDLE)

        return actions
