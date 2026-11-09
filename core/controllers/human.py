import pygame

from core.vos.action import Action
from core.vos.gamestate import Gamestate
from ports.controller import Controller


class Human(Controller):
    def get_actions(self, state: Gamestate, player_id: int) -> list[Action]:
        actions = []

        keys = pygame.key.get_pressed()

        if keys[pygame.K_UP] or keys[pygame.K_w]:
            actions.append(Action.UP)
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            actions.append(Action.DOWN)
        elif keys[pygame.K_LEFT] or keys[pygame.K_l]:
            actions.append(Action.LEFT)
        elif keys[pygame.K_RIGHT] or keys[pygame.K_r]:
            actions.append(Action.RIGHT)
            
        if keys[pygame.K_SPACE]:
            actions.append(Action.BOMB)

        if not actions:
            actions.append(Action.IDLE)

        return actions
