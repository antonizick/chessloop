import json
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
import chess

from database import get_session
from models import User, Game
from models.game import STARTING_FEN
from auth.dependencies import get_current_user
from services.activity_log import log_activity
from schemas.game import (
    GameCreate,
    GameUpdate,
    GameMovesImport,
    GameMoveNoteUpdate,
    GameMoveAppend,
    GameResponse,
)

router = APIRouter(tags=["games"])


def _owned_game_or_404(session: Session, game_id: UUID, user: User) -> Game:
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    if game.owner_user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
    return game


def _build_move_records(starting_fen: str, sans: list[str]) -> list[dict]:
    """Validate a SAN list against the starting position and produce move records."""
    board = chess.Board(starting_fen)
    records: list[dict] = []
    for san in sans:
        try:
            move = board.parse_san(san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid SAN '{san}': {exc}")
        uci = move.uci()
        board.push(move)
        records.append({"san": san, "uci": uci, "fen_after": board.fen()})
    return records


@router.get("/games", response_model=list[GameResponse])
def list_games(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Game)
        .where(Game.owner_user_id == user.id)
        .order_by(Game.played_date.desc(), Game.created_at.desc())
    ).all()


@router.post("/games", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
def create_game(
    body: GameCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    start_fen = body.starting_fen or STARTING_FEN
    records = _build_move_records(start_fen, body.moves)
    game = Game(
        owner_user_id=user.id,
        name=body.name,
        played_date=body.played_date,
        played_color=body.played_color,
        opponent_level=body.opponent_level,
        result=body.result,
        what_happened=body.what_happened,
        lesson_learned=body.lesson_learned,
        repeat_offense=body.repeat_offense,
        starting_fen=start_fen,
        moves=json.dumps(records),
    )
    session.add(game)
    session.commit()
    session.refresh(game)
    log_activity(session, user.id, user.username, "create_game", target=game.name)
    return game


@router.get("/games/{game_id}", response_model=GameResponse)
def get_game(
    game_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _owned_game_or_404(session, game_id, user)


@router.put("/games/{game_id}", response_model=GameResponse)
def update_game(
    game_id: UUID,
    body: GameUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(game, field, value)
    game.updated_at = datetime.utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@router.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(
    game_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    name = game.name
    session.delete(game)
    session.commit()
    log_activity(session, user.id, user.username, "delete_game", target=name)


@router.put("/games/{game_id}/moves", response_model=GameResponse)
def replace_moves(
    game_id: UUID,
    body: GameMovesImport,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    start_fen = body.starting_fen or game.starting_fen
    records = _build_move_records(start_fen, body.moves)
    if body.starting_fen:
        game.starting_fen = body.starting_fen
    game.moves = json.dumps(records)
    game.updated_at = datetime.utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@router.post("/games/{game_id}/moves", response_model=GameResponse)
def append_move(
    game_id: UUID,
    body: GameMoveAppend,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    moves = json.loads(game.moves or "[]")

    if body.uci is None or body.fen_after is None:
        board = chess.Board(game.starting_fen)
        for m in moves:
            board.push_san(m["san"])
        try:
            move = board.parse_san(body.san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid SAN '{body.san}': {exc}")
        uci = move.uci()
        board.push(move)
        fen_after = board.fen()
    else:
        uci = body.uci
        fen_after = body.fen_after

    record = {"san": body.san, "uci": uci, "fen_after": fen_after}
    if body.note:
        record["note"] = body.note
    moves.append(record)
    game.moves = json.dumps(moves)
    game.updated_at = datetime.utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@router.delete("/games/{game_id}/moves/{index}", response_model=GameResponse)
def delete_move(
    game_id: UUID,
    index: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    moves = json.loads(game.moves or "[]")
    if index < 0 or index >= len(moves):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Move index out of range")
    del moves[index:]  # delete this move and everything after — keep game valid
    game.moves = json.dumps(moves)
    game.updated_at = datetime.utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@router.put("/games/{game_id}/moves/{index}/note", response_model=GameResponse)
def update_move_note(
    game_id: UUID,
    index: int,
    body: GameMoveNoteUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    game = _owned_game_or_404(session, game_id, user)
    moves = json.loads(game.moves or "[]")
    if index < 0 or index >= len(moves):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Move index out of range")
    if body.text:
        moves[index]["note"] = body.text
    else:
        moves[index].pop("note", None)
    game.moves = json.dumps(moves)
    game.updated_at = datetime.utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return game
