from __future__ import annotations

from dataclasses import dataclass
import random
from typing import List, Optional, Sequence, Tuple

Point = Tuple[int, int]
Direction = str

DIR_UP: Direction = "UP"
DIR_DOWN: Direction = "DOWN"
DIR_LEFT: Direction = "LEFT"
DIR_RIGHT: Direction = "RIGHT"

DIR_DELTAS = {
    DIR_UP: (0, -1),
    DIR_DOWN: (0, 1),
    DIR_LEFT: (-1, 0),
    DIR_RIGHT: (1, 0),
}

OPPOSITES = {
    DIR_UP: DIR_DOWN,
    DIR_DOWN: DIR_UP,
    DIR_LEFT: DIR_RIGHT,
    DIR_RIGHT: DIR_LEFT,
}


@dataclass(frozen=True)
class SnakeConfig:
    cols: int = 20
    rows: int = 20


@dataclass(frozen=True)
class SnakeState:
    snake: Tuple[Point, ...]
    direction: Direction
    food: Optional[Point]
    score: int
    game_over: bool
    paused: bool = False


def create_initial_state(config: SnakeConfig, rng: Optional[random.Random] = None) -> SnakeState:
    cx = config.cols // 2
    cy = config.rows // 2
    snake: Tuple[Point, ...] = ((cx, cy), (cx - 1, cy), (cx - 2, cy))
    food = place_food(config, snake, rng=rng)
    return SnakeState(
        snake=snake,
        direction=DIR_RIGHT,
        food=food,
        score=0,
        game_over=False,
        paused=False,
    )


def normalize_direction(current: Direction, requested: Optional[Direction], snake_len: int) -> Direction:
    if not requested or requested not in DIR_DELTAS:
        return current
    if snake_len > 1 and OPPOSITES.get(current) == requested:
        return current
    return requested


def toggle_pause(state: SnakeState) -> SnakeState:
    if state.game_over:
        return state
    return SnakeState(
        snake=state.snake,
        direction=state.direction,
        food=state.food,
        score=state.score,
        game_over=False,
        paused=not state.paused,
    )


def step_game(
    state: SnakeState,
    config: SnakeConfig,
    requested_direction: Optional[Direction] = None,
    rng: Optional[random.Random] = None,
) -> SnakeState:
    if state.game_over or state.paused:
        direction = normalize_direction(state.direction, requested_direction, len(state.snake))
        return SnakeState(
            snake=state.snake,
            direction=direction,
            food=state.food,
            score=state.score,
            game_over=state.game_over,
            paused=state.paused,
        )

    direction = normalize_direction(state.direction, requested_direction, len(state.snake))
    dx, dy = DIR_DELTAS[direction]
    head_x, head_y = state.snake[0]
    new_head = (head_x + dx, head_y + dy)

    if not in_bounds(new_head, config):
        return SnakeState(
            snake=state.snake,
            direction=direction,
            food=state.food,
            score=state.score,
            game_over=True,
            paused=False,
        )

    will_grow = state.food is not None and new_head == state.food
    body_to_check = state.snake if will_grow else state.snake[:-1]
    if new_head in body_to_check:
        return SnakeState(
            snake=state.snake,
            direction=direction,
            food=state.food,
            score=state.score,
            game_over=True,
            paused=False,
        )

    if will_grow:
        new_snake = (new_head,) + state.snake
        next_food = place_food(config, new_snake, rng=rng)
        game_over = next_food is None
        return SnakeState(
            snake=new_snake,
            direction=direction,
            food=next_food,
            score=state.score + 1,
            game_over=game_over,
            paused=False,
        )

    moved_snake = (new_head,) + state.snake[:-1]
    return SnakeState(
        snake=moved_snake,
        direction=direction,
        food=state.food,
        score=state.score,
        game_over=False,
        paused=False,
    )


def in_bounds(point: Point, config: SnakeConfig) -> bool:
    x, y = point
    return 0 <= x < config.cols and 0 <= y < config.rows


def place_food(
    config: SnakeConfig,
    snake: Sequence[Point],
    rng: Optional[random.Random] = None,
) -> Optional[Point]:
    occupied = set(snake)
    empty: List[Point] = [
        (x, y)
        for y in range(config.rows)
        for x in range(config.cols)
        if (x, y) not in occupied
    ]
    if not empty:
        return None
    chooser = rng if rng is not None else random
    return chooser.choice(empty)
