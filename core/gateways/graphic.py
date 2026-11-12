from __future__ import annotations

import math
import os
from typing import Any, Final

import pygame

from core.commands.gamerules import (
    FLAME_DURATION_TICKS,
    SUDDEN_DEATH_START_TICK,
    compute_danger_map,
    get_upcoming_sudden_death_tiles,
)
from core.entities.bomb import Bomb
from core.entities.player import Player
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.powerup import PowerUpType
from core.vos.walls import Wall

EMPTY_SPRITE_PATH: Final = os.path.join("./src/empty.png")
CONCRETE_SPRITE_PATH: Final = os.path.join("./src/concrete.png")
BOX_SPRITE_PATH: Final = os.path.join("./src/box.png")
BOMB_SPRITE_PATH: Final = os.path.join("./src/bomb.breno.png")

EXPLOSION_SPRITE_PATH_BASE: Final = "./src/explosion"
EXPLOSION_SPRITES_NUMBER = 10
EXPLOSION_SPRITES_PER_TICK = 2

PLAYER_SPRITE_PATH_BASE: Final = "./src/p1"

# Distinct colors for P1, P2, P3, P4
PLAYER_COLORS: Final[list[tuple[int, int, int]]] = [
    (66, 165, 245),   # P1: Vibrant Blue
    (239, 83, 80),    # P2: Crimson Red
    (102, 187, 106),  # P3: Emerald Green
    (255, 202, 40),   # P4: Amber Gold
]

POWERUP_STYLES: Final[dict[PowerUpType, tuple[tuple[int, int, int], str]]] = {
    PowerUpType.BOMB_UP: ((41, 182, 246), "+B"),
    PowerUpType.FIRE_UP: ((255, 112, 67), "+F"),
    PowerUpType.SPEED_UP: ((156, 204, 101), "+S"),
}


class Graphic:
    wall_sprites: dict[Wall, pygame.Surface]
    fire_sprites: list[pygame.Surface]
    player_sprites: dict[Direction, pygame.Surface]
    tinted_player_sprites: dict[tuple[int, Direction], pygame.Surface]
    bomb_sprite: pygame.Surface

    temp_players: list[Player]

    screen: pygame.Surface
    scale: int = 64
    hud_width: int = 310

    def __init__(
        self,
        scale: int,
        rows: int,
        colums: int,
        players: list[Player] | None = None,
    ) -> None:
        pygame.font.init()
        self.scale = scale
        self.grid_px_w = rows * scale
        self.grid_px_h = colums * scale
        screen_width = self.grid_px_w + self.hud_width
        screen_height = max(self.grid_px_h, 576)

        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("DynamiteMan - PvP & Tabular Q-Learning AI Showcase")

        self.font_title = pygame.font.SysFont("monospace", 18, bold=True)
        self.font_body = pygame.font.SysFont("monospace", 14, bold=True)
        self.font_small = pygame.font.SysFont("monospace", 12, bold=False)
        self.font_banner = pygame.font.SysFont("monospace", 26, bold=True)

        self.wall_sprites = {}
        self.wall_sprites[Wall.EMPTY] = pygame.image.load(EMPTY_SPRITE_PATH).convert_alpha()
        self.wall_sprites[Wall.CONCRETE] = pygame.image.load(CONCRETE_SPRITE_PATH).convert_alpha()
        self.wall_sprites[Wall.BOX] = pygame.image.load(BOX_SPRITE_PATH).convert_alpha()

        raw_bomb = pygame.image.load(BOMB_SPRITE_PATH).convert_alpha()
        self.bomb_sprite = pygame.transform.smoothscale(
            raw_bomb, (int(scale * 0.85), int(scale * 0.60))
        )

        self.load_explosion_sprites()
        self.load_player_sprites()
        self.temp_players = players or []
        self._frame_counter = 0

    def draw(
        self,
        gs: Gamestate,
        sub_frame_ratio: float = 0.0,
        hud_info: dict[str, Any] | None = None,
    ) -> None:
        self._frame_counter += 1
        self.screen.fill((24, 26, 32))

        self.draw_grid(gs.grid_walls)
        self.draw_danger_preview(gs)
        self.draw_sudden_death_warning(gs)
        self.draw_powerups(gs.powerups)
        self.draw_bombs(gs.bombs)
        self.draw_fire(gs.flames_grid, sub_frame_ratio=sub_frame_ratio)

        players_to_draw = gs.players if gs.players else self.temp_players
        self.draw_players(players_to_draw, sub_frame_ratio=sub_frame_ratio)
        self.draw_hud(gs, players_to_draw, hud_info or {})

        if gs.is_over:
            self.draw_match_over_banner(gs, hud_info or {})

        pygame.display.flip()

    def draw_grid(self, walls: list[list[Wall]]) -> None:
        for idy, row in enumerate(walls):
            for idx, wall_type in enumerate(row):
                pos = self.pos(idx, idy)
                self.screen.blit(self.wall_sprites[wall_type], pos)

    def draw_danger_preview(self, gs: Gamestate) -> None:
        if not gs.bombs:
            return
        danger = compute_danger_map(gs)
        overlay = pygame.Surface((self.scale, self.scale), pygame.SRCALPHA)
        for (x, y), fuse in danger.items():
            if fuse <= 0:
                continue
            alpha = 70 if fuse <= 2 else 38
            overlay.fill((255, 60, 40, alpha))
            self.screen.blit(overlay, self.pos(x, y))

    def draw_sudden_death_warning(self, gs: Gamestate) -> None:
        upcoming = get_upcoming_sudden_death_tiles(gs, lookahead=4)
        if not upcoming:
            return
        for sx, sy, ticks_left in upcoming:
            px, py = self.pos(sx, sy)
            rect = pygame.Rect(px + 2, py + 2, self.scale - 4, self.scale - 4)
            color = (255, 82, 82) if ticks_left <= 1 else (255, 193, 7)
            pygame.draw.rect(self.screen, color, rect, 3, border_radius=4)
            lbl = self.font_small.render(f"SD:{ticks_left}", True, color)
            self.screen.blit(lbl, (px + 6, py + 6))

    def draw_powerups(
        self, powerups: dict[tuple[int, int], PowerUpType]
    ) -> None:
        if not powerups:
            return
        bob = int(3.0 * math.sin(self._frame_counter * 0.2))
        for (x, y), ptype in powerups.items():
            px, py = self.pos(x, y)
            cx = px + self.scale // 2
            cy = py + self.scale // 2 + bob
            color, label = POWERUP_STYLES.get(ptype, ((255, 255, 255), "+P"))
            pygame.draw.circle(self.screen, (20, 22, 28), (cx, cy), 17)
            pygame.draw.circle(self.screen, color, (cx, cy), 15)
            pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), 15, 2)
            txt = self.font_body.render(label, True, (15, 18, 24))
            self.screen.blit(
                txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2)
            )

    def draw_bombs(self, bombs: list[Bomb]) -> None:
        for b in bombs:
            bx, by = self.pos(b.pos.x, b.pos.y)
            pulse = 1.0 + 0.08 * math.sin(self._frame_counter * 0.35)
            w = int(self.bomb_sprite.get_width() * pulse)
            h = int(self.bomb_sprite.get_height() * pulse)
            scaled = pygame.transform.smoothscale(self.bomb_sprite, (w, h))
            offset_x = bx + (self.scale - w) // 2
            offset_y = by + (self.scale - h) // 2 + 4
            self.screen.blit(scaled, (offset_x, offset_y))

            owner_color = PLAYER_COLORS[b.owner_id % len(PLAYER_COLORS)]
            pygame.draw.circle(
                self.screen,
                owner_color,
                (bx + 12, by + 12),
                9,
            )
            pygame.draw.circle(
                self.screen,
                (15, 15, 20),
                (bx + 12, by + 12),
                9,
                2,
            )
            fuse_txt = self.font_small.render(
                str(max(0, b.fuse_ticks)), True, (15, 15, 20)
            )
            self.screen.blit(fuse_txt, (bx + 9, by + 5))

    def draw_fire(
        self, fire_ticks: list[list[int]], sub_frame_ratio: float = 0.0
    ) -> None:
        for idy, row in enumerate(fire_ticks):
            for idx, cf in enumerate(row):
                if cf == -1:
                    continue

                pos = self.pos(idx, idy)
                if cf <= FLAME_DURATION_TICKS:
                    progress = (
                        (FLAME_DURATION_TICKS - cf + sub_frame_ratio)
                        / max(1.0, float(FLAME_DURATION_TICKS))
                    )
                    frame_number = int(progress * (EXPLOSION_SPRITES_NUMBER - 1))
                else:
                    frame_number = abs(
                        (cf // EXPLOSION_SPRITES_PER_TICK) - EXPLOSION_SPRITES_NUMBER
                    )
                frame_number = max(0, min(frame_number, EXPLOSION_SPRITES_NUMBER - 1))

                self.screen.blit(self.fire_sprites[frame_number], pos)

    def draw_players(
        self, players: list[Player], sub_frame_ratio: float = 0.0
    ) -> None:
        t = max(0.0, min(1.0, sub_frame_ratio))
        for p in players:
            color = PLAYER_COLORS[p.id % len(PLAYER_COLORS)]

            if not p.alive:
                px, py = self.pos(p.pos.x, p.pos.y)
                center = (px + self.scale // 2, py + self.scale // 2)
                pygame.draw.circle(self.screen, (40, 40, 48), center, 14)
                pygame.draw.circle(self.screen, color, center, 14, 2)
                pygame.draw.line(
                    self.screen,
                    color,
                    (center[0] - 6, center[1] - 6),
                    (center[0] + 6, center[1] + 6),
                    3,
                )
                pygame.draw.line(
                    self.screen,
                    color,
                    (center[0] + 6, center[1] - 6),
                    (center[0] - 6, center[1] + 6),
                    3,
                )
                continue

            # Smoothly interpolate pixel position from prev_pos to pos across the tick
            prev_pos = getattr(p, "prev_pos", p.pos)
            fx = float(prev_pos.x) + (float(p.pos.x) - float(prev_pos.x)) * t
            fy = float(prev_pos.y) + (float(p.pos.y) - float(prev_pos.y)) * t
            px = int(round(fx * self.scale))
            py = int(round(fy * self.scale))

            # Subtle stride hop when moving between cells
            is_moving = (prev_pos.x != p.pos.x) or (prev_pos.y != p.pos.y)
            stride_hop = int(round(4.0 * math.sin(t * math.pi))) if is_moving else 0

            pygame.draw.ellipse(
                self.screen,
                color,
                pygame.Rect(px + 10, py + self.scale - 16, self.scale - 20, 12),
                3,
            )

            sprite = self.tinted_player_sprites.get(
                (p.id % len(PLAYER_COLORS), p.facing),
                self.player_sprites[p.facing],
            )
            self.screen.blit(sprite, (px + 2, py + 2 - stride_hop))

            tag_bg = pygame.Rect(px + 16, py + 1 - stride_hop, 32, 14)
            pygame.draw.rect(self.screen, color, tag_bg, border_radius=4)
            pygame.draw.rect(self.screen, (20, 20, 25), tag_bg, 1, border_radius=4)
            tag_txt = self.font_small.render(f"P{p.id + 1}", True, (15, 15, 20))
            self.screen.blit(tag_txt, (px + 25, py + 1 - stride_hop))

    def draw_hud(
        self,
        gs: Gamestate,
        players: list[Player],
        hud_info: dict[str, Any],
    ) -> None:
        panel_x = self.grid_px_w
        panel_rect = pygame.Rect(panel_x, 0, self.hud_width, self.screen.get_height())
        pygame.draw.rect(self.screen, (28, 31, 40), panel_rect)
        pygame.draw.line(
            self.screen,
            (70, 76, 95),
            (panel_x, 0),
            (panel_x, self.screen.get_height()),
            2,
        )

        x = panel_x + 14
        y = 12

        title = self.font_title.render("DYNAMITEMAN AI ARENA", True, (245, 247, 250))
        self.screen.blit(title, (x, y))
        y += 24

        mode_str = hud_info.get("mode", "4 AI Battle")
        round_num = hud_info.get("round", 1)
        tps = hud_info.get("tps", 7)

        sub1 = self.font_body.render(f"Mode: {mode_str}", True, (129, 212, 250))
        self.screen.blit(sub1, (x, y))
        y += 18

        sd_active = gs.current_tick >= SUDDEN_DEATH_START_TICK
        sd_tag = " [SUDDEN DEATH!]" if sd_active else ""
        sub2_color = (255, 112, 67) if sd_active else (190, 198, 212)
        sub2 = self.font_small.render(
            f"R#{round_num} | Tick {gs.current_tick}/{gs.max_ticks} ({tps}t/s){sd_tag}",
            True,
            sd_color if (sd_color := sub2_color) else (190, 198, 212),
        )
        self.screen.blit(sub2, (x, y))
        y += 20

        q_box = pygame.Rect(x, y, self.hud_width - 28, 76)
        pygame.draw.rect(self.screen, (38, 43, 56), q_box, border_radius=6)
        pygame.draw.rect(self.screen, (88, 101, 242), q_box, 1, border_radius=6)

        episodes = hud_info.get("episodes", 0)
        q_states = hud_info.get("q_states", 0)
        stat_label = hud_info.get("stat_label", f"Learned States: {q_states}")
        agent_title = hud_info.get("agent_title", "Tabular Q-Learning Agent")
        train_time = hud_info.get("train_time_s", 0.0)
        vs_human_wr = hud_info.get("vs_human_wr", 0.0)

        q_lines = [
            agent_title,
            f"Trained: {episodes} eps ({train_time:.1f}s)",
            stat_label,
            f"WinRate vs Heuristic: {vs_human_wr:.0f}%",
        ]
        qy = y + 6
        for idx_l, line in enumerate(q_lines):
            clr = (255, 213, 79) if idx_l == 0 else (215, 222, 235)
            surf = self.font_small.render(line, True, clr)
            self.screen.blit(surf, (x + 8, qy))
            qy += 16

        y += 84

        wins_map: dict[int, int] = hud_info.get("wins", {})
        human_id: int | None = hud_info.get("human_id", None)
        role_labels: dict[int, str] = hud_info.get("role_labels", {})

        for p in players:
            card_rect = pygame.Rect(x, y, self.hud_width - 28, 68)
            color = PLAYER_COLORS[p.id % len(PLAYER_COLORS)]
            bg_color = (42, 47, 60) if p.alive else (32, 33, 40)
            pygame.draw.rect(self.screen, bg_color, card_rect, border_radius=6)
            pygame.draw.rect(
                self.screen,
                color if p.alive else (80, 80, 90),
                card_rect,
                2 if p.alive else 1,
                border_radius=6,
            )

            role_label = (
                "YOU (Human)"
                if human_id == p.id
                else role_labels.get(p.id, "RL Agent AI")
            )
            status_str = "ALIVE" if p.alive else "DEAD"
            status_clr = (102, 187, 106) if p.alive else (239, 83, 80)

            p_title = self.font_body.render(
                f"P{p.id + 1} [{role_label}]", True, color
            )
            self.screen.blit(p_title, (x + 8, y + 6))

            st_surf = self.font_body.render(status_str, True, status_clr)
            self.screen.blit(
                st_surf, (x + self.hud_width - 36 - st_surf.get_width(), y + 6)
            )

            p_wins = wins_map.get(p.id, 0)
            stats_line = self.font_small.render(
                f"Wins: {p_wins} | Kills: {p.kills} | Boxes: {p.boxes_destroyed}",
                True,
                (220, 224, 232),
            )
            self.screen.blit(stats_line, (x + 8, y + 27))

            pos_line = self.font_small.render(
                f"Bombs:{p.active_bombs}/{p.bomb_capacity} | Fire:{p.blast_radius} | Spd:{p.speed}",
                True,
                (170, 178, 195),
            )
            self.screen.blit(pos_line, (x + 8, y + 45))

            y += 74

        controls = [
            "Controls:",
            "[M] Switch 4-AI / Human+3AI",
            "[WASD/Arrows + Space] Human",
            "[+/-] Speed  [R] New Round",
            "[T] +200 Train Eps  [ESC] Quit",
        ]
        cy = self.screen.get_height() - len(controls) * 15 - 8
        for idx_c, cline in enumerate(controls):
            c_clr = (144, 202, 249) if idx_c == 0 else (165, 175, 190)
            c_surf = self.font_small.render(cline, True, c_clr)
            self.screen.blit(c_surf, (x, cy))
            cy += 15

    def draw_match_over_banner(
        self, gs: Gamestate, hud_info: dict[str, Any]
    ) -> None:
        overlay = pygame.Surface((self.grid_px_w, 90), pygame.SRCALPHA)
        overlay.fill((15, 17, 24, 215))
        by = (self.grid_px_h - 90) // 2
        self.screen.blit(overlay, (0, by))

        if gs.winner_id is not None:
            human_id = hud_info.get("human_id", None)
            role_labels: dict[int, str] = hud_info.get("role_labels", {})
            role = (
                "HUMAN"
                if human_id == gs.winner_id
                else role_labels.get(gs.winner_id, "RL AI").upper()
            )
            text = f"PLAYER {gs.winner_id + 1} ({role}) WINS!"
            color = PLAYER_COLORS[gs.winner_id % len(PLAYER_COLORS)]
        else:
            text = "ROUND DRAW!"
            color = (220, 220, 230)

        banner_surf = self.font_banner.render(text, True, color)
        bx = (self.grid_px_w - banner_surf.get_width()) // 2
        self.screen.blit(banner_surf, (bx, by + 18))

        sub_surf = self.font_body.render(
            "Next round starting soon... (or press [R] now)",
            True,
            (200, 205, 215),
        )
        sx = (self.grid_px_w - sub_surf.get_width()) // 2
        self.screen.blit(sub_surf, (sx, by + 54))

    def pos(self, x: int, y: int) -> tuple[int, int]:
        return x * self.scale, y * self.scale

    def load_explosion_sprites(self) -> None:
        self.fire_sprites = []
        for n in range(1, EXPLOSION_SPRITES_NUMBER + 1):
            path = os.path.join(f"{EXPLOSION_SPRITE_PATH_BASE}{n}.png")
            self.fire_sprites.append(pygame.image.load(path).convert_alpha())

    def load_player_sprites(self) -> None:
        self.player_sprites = {}
        self.tinted_player_sprites = {}

        for d in [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]:
            path = os.path.join(f"{PLAYER_SPRITE_PATH_BASE}{d}.png")
            base_surf = pygame.image.load(path).convert_alpha()
            self.player_sprites[d] = base_surf

            for p_idx, color in enumerate(PLAYER_COLORS):
                tinted = base_surf.copy()
                tint_surf = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
                tint_surf.fill((*color, 55))
                tinted.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self.tinted_player_sprites[(p_idx, d)] = tinted
