# def clone() -> GameState
# def reset_tick_cache()
# def is_walkable(x, y) -> bool
# def is_flame(x, y) -> bool
import math

from core.vos.action import Action
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall
from core.entities.player import Player
from core.entities.bomb import Bomb
from core.vos.direction import Direction

MOVE_DELTAS = {
    Action.UP: (0, -1, Direction.DOWN),
    Action.DOWN: (0, 1, Direction.UP),
    Action.LEFT: (-1, 0, Direction.LEFT),
    Action.RIGHT: (1, 0, Direction.RIGHT),
}

STEP_SIZE = 0.1
CORNER_TOLERANCE = 0.45
FIRE_DURATION_TICKS = 20  # Casa com os 10 sprites de explosão do Graphic


def is_flame(gs: Gamestate, x: int, y: int) -> bool:
    if not (0 <= x < gs.width and 0 <= y < gs.height):
        return False
    return gs.flames_grid[y][x] >= 0

#Diminui o tempo do fogo ativo até apagar (-1)
def process_fires(gs: Gamestate) -> None:
    for y in range(gs.height):
        for x in range(gs.width):
            if gs.flames_grid[y][x] >= 0:
                gs.flames_grid[y][x] -= 1
                
#Gera a explosão em cruz, destrói caixas e devolve capacidade ao dono                
def explode_bomb(gs: Gamestate, bomb: Bomb) -> None:
    
    # Devolve 1 bomba para o jogador dono poder plantar de novo
    for p in gs.players:
        if p.id == bomb.owner_id:
            p.active_bombs = max(0, p.active_bombs - 1)
            break
    bx, by = int(bomb.pos.x), int(bomb.pos.y)
    gs.flames_grid[by][bx] = FIRE_DURATION_TICKS
    
    # Espalha o fogo nas 4 direções (cima, baixo, esquerda, direita)
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        for dist in range(1, bomb.blast_radius + 1):
            fx = bx + dx * dist
            fy = by + dy * dist
            if not (0 <= fx < gs.width and 0 <= fy < gs.height):
                break
            
            # Concreto bloqueia a explosão
            if gs.grid_walls[fy][fx] == Wall.CONCRETE:
                break
            gs.flames_grid[fy][fx] = FIRE_DURATION_TICKS
            
            # Reação em cadeia: se atingir outra bomba, ela explode junto
            for other in gs.bombs:
                if int(other.pos.x) == fx and int(other.pos.y) == fy:
                    other.fuse_ticks = 0
            
            # Caixa é destruída e segura o resto da chama naquela direção
            if gs.grid_walls[fy][fx] == Wall.BOX:
                gs.grid_walls[fy][fx] = Wall.EMPTY
                break
            
#Reduz os ticks das bombas e explode as que chegaram a 0      
def process_bombs(gs: Gamestate) -> None:
    
    for b in gs.bombs:
        b.fuse_ticks -= 1
    
    # Loop while garante que bombas em reação em cadeia explodam no mesmo tick
    while True:
        exploding = [b for b in gs.bombs if b.fuse_ticks <= 0]
        if not exploding:
            break
        for b in exploding:
            gs.bombs.remove(b)
            explode_bomb(gs, b)


def is_walkable(gs: Gamestate, x: int, y: int, player: Player | None = None) -> bool:
    
    #Fora do mapa
    if not (0 <= x < gs.width and 0 <= y < gs.height):
        return False
    
    #Se tem parede no caminho
    if gs.grid_walls[y][x] != Wall.EMPTY:
        return False
    
    #Se tem uma bomba no caminho
    if any(b.pos.x == x and b.pos.y == y for b in gs.bombs):
        if player is not None:
            
            #Continua em cima da bomba e não saiu?
            still_on_bomb = (
                math.floor(player.pos.x) <= x <= math.ceil(player.pos.x)
                and math.floor(player.pos.y) <= y <= math.ceil(player.pos.y)
            )
            if still_on_bomb:
                return True
        return False
    
    #Se tem outros jogadores
    for other in gs.players:
        if not other.alive:
            continue
        if player is not None and other.id == player.id:
            continue
        if (
            math.floor(other.pos.x) <= x <= math.ceil(other.pos.x) and
            math.floor(other.pos.y) <= y <= math.ceil(other.pos.y)
        ): 
            return False
        
    return True

#Verifica se é possível fazer aquela movimentação
def try_move(gs: Gamestate, player: Player, dx: int, dy: int) -> bool:
    
    step = STEP_SIZE * player.speed
    x, y = player.pos.x, player.pos.y
    
    
    if dx != 0:
        new_x = max(0.0, min(float(gs.width - 1), round(x + dx * step, 3)))
        check_x = math.ceil(new_x) if dx > 0 else math.floor(new_x)
        top_y, bottom_y = math.floor(y), math.ceil(y)

        if is_walkable(gs, check_x, top_y, player) and is_walkable(gs, check_x, bottom_y, player):
            player.pos = Position(new_x, y)
            return True

        nearest_y = round(y)
        
        if abs(y - nearest_y) <= CORNER_TOLERANCE and is_walkable(gs, check_x, nearest_y, player):
            if abs(y - nearest_y) <= step:
                player.pos = Position(new_x, float(nearest_y))
            else:
                slide_y = round(y + (step if nearest_y > y else -step), 3)
                player.pos = Position(x, slide_y)
            return True
        
    elif dy != 0:
        new_y = max(0.0, min(float(gs.height - 1), round(y + dy * step, 3)))
        check_y = math.ceil(new_y) if dy > 0 else math.floor(new_y)
        left_x, right_x = math.floor(x), math.ceil(x)

        if is_walkable(gs, left_x, check_y, player) and is_walkable(gs, right_x, check_y, player):
            player.pos = Position(x, new_y)
            return True

        nearest_x = round(x)
        if abs(x - nearest_x) <= CORNER_TOLERANCE and is_walkable(gs, nearest_x, check_y, player):
            if abs(x - nearest_x) <= step:
                player.pos = Position(float(nearest_x), new_y)
            else:
                slide_x = round(x + (step if nearest_x > x else -step), 3)
                player.pos = Position(slide_x, y)
            return True
    return False


def plant_bomb(gs: Gamestate, player: Player) -> None:
    
    #Não planta se o jogador tiver mais bombas ativas do que capacidade 
    if player.active_bombs >= player.bomb_capacity:
        return

    bx, by = player.pos.grid()

    # Não planta se já existir bomba nessa célula
    if any(b.pos.x == bx and b.pos.y == by for b in gs.bombs):
        return

    gs.bombs.append(
        Bomb(
            id=gs.current_tick,
            owner_id=player.id,
            pos=Position(bx, by),
            fuse_ticks=120,
            blast_radius=2,
        )
    )
    player.active_bombs += 1


def update_gamestate(gs: Gamestate) -> None:
    gs.current_tick += 1
    
    process_fires(gs)
    process_bombs(gs)
    
    for player in gs.players:
        if not player.alive:
            continue
        actions = player.controller.get_actions(gs, player.id)
        move_actions = [a for a in actions if a in MOVE_DELTAS]
        move_actions.sort(key=lambda a: MOVE_DELTAS[a][2] == player.facing)
        for action in move_actions:
            dx, dy, direction = MOVE_DELTAS[action]
            player.facing = direction
            if try_move(gs, player, dx, dy):
                break
        if Action.BOMB in actions:
            plant_bomb(gs, player)
            
        px, py = player.pos.grid()
        if is_flame(gs, px, py):
            player.alive = False
