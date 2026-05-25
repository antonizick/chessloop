from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from database import get_session
from models import User, Library, Line
from models.public_signal import PublicSignal
from auth.dependencies import get_current_user
from schemas.public import (
    PublicLibraryEntry,
    PublicLibraryDetail,
    CommentEntry,
    CommentCreate,
)

router = APIRouter(prefix="/public", tags=["public"])


def _star_count(db: Session, library_id: UUID) -> int:
    return len(db.exec(
        select(PublicSignal).where(
            PublicSignal.target_type == "library",
            PublicSignal.target_id == library_id,
            PublicSignal.kind == "star",
        )
    ).all())


def _line_count(db: Session, library_id: UUID) -> int:
    return len(db.exec(select(Line).where(Line.library_id == library_id)).all())


def _get_public_lib(db: Session, lib_id: UUID) -> Library:
    lib = db.get(Library, lib_id)
    if not lib or not lib.is_public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found or not public")
    return lib


@router.get("/libraries", response_model=list[PublicLibraryEntry])
def browse_public(
    q: str = Query(default=""),
    eco: str = Query(default=""),
    color: str = Query(default=""),
    difficulty: str = Query(default=""),
    sort: str = Query(default="stars"),   # 'stars' | 'newest' | 'name' | 'lines'
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Library).where(Library.is_public == True)  # noqa: E712
    if q:
        stmt = stmt.where(Library.name.contains(q))
    if eco:
        stmt = stmt.where(Library.eco_code == eco.upper())
    if color and color in ("white", "black", "both"):
        stmt = stmt.where(Library.color == color)
    if difficulty and difficulty in ("beginner", "intermediate", "advanced"):
        stmt = stmt.where(Library.difficulty == difficulty)

    libraries = db.exec(stmt).all()

    result = []
    seen_ids = set()  # Deduplicate by library ID
    for lib in libraries:
        if lib.id in seen_ids:
            continue
        seen_ids.add(lib.id)

        owner = db.get(User, lib.owner_user_id)
        result.append(PublicLibraryEntry(
            id=lib.id,
            name=lib.name,
            color=lib.color,
            description=lib.description,
            eco_code=lib.eco_code,
            difficulty=lib.difficulty,
            owner_username=owner.username if owner else "unknown",
            published_at=lib.published_at,
            star_count=_star_count(db, lib.id),
            line_count=_line_count(db, lib.id),
            forked_from_id=lib.forked_from_id,
        ))

    # Sort by the specified criteria
    if sort == "newest":
        result.sort(key=lambda x: x.published_at, reverse=True)
    elif sort == "name":
        result.sort(key=lambda x: x.name.lower())
    elif sort == "lines":
        result.sort(key=lambda x: x.line_count, reverse=True)
    else:  # default to stars
        result.sort(key=lambda x: x.star_count, reverse=True)

    return result


@router.get("/libraries/{lib_id}", response_model=PublicLibraryDetail)
def get_public_library(
    lib_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    lib = _get_public_lib(db, lib_id)
    owner = db.get(User, lib.owner_user_id)

    user_starred = bool(db.exec(
        select(PublicSignal).where(
            PublicSignal.target_type == "library",
            PublicSignal.target_id == lib.id,
            PublicSignal.kind == "star",
            PublicSignal.user_id == user.id,
        )
    ).first())

    comment_signals = db.exec(
        select(PublicSignal).where(
            PublicSignal.target_type == "library",
            PublicSignal.target_id == lib.id,
            PublicSignal.kind == "comment",
        )
    ).all()
    comment_signals.sort(key=lambda x: x.created_at)

    comments = []
    for sig in comment_signals:
        commenter = db.get(User, sig.user_id)
        comments.append(CommentEntry(
            id=sig.id,
            username=commenter.username if commenter else "unknown",
            content=sig.content or "",
            created_at=sig.created_at,
        ))

    return PublicLibraryDetail(
        id=lib.id,
        name=lib.name,
        color=lib.color,
        description=lib.description,
        eco_code=lib.eco_code,
        difficulty=lib.difficulty,
        owner_username=owner.username if owner else "unknown",
        published_at=lib.published_at,
        star_count=_star_count(db, lib.id),
        line_count=_line_count(db, lib.id),
        forked_from_id=lib.forked_from_id,
        user_has_starred=user_starred,
        comments=comments,
    )


@router.post("/libraries/{lib_id}/star", status_code=status.HTTP_204_NO_CONTENT)
def toggle_star(
    lib_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _get_public_lib(db, lib_id)

    existing = db.exec(
        select(PublicSignal).where(
            PublicSignal.target_type == "library",
            PublicSignal.target_id == lib_id,
            PublicSignal.kind == "star",
            PublicSignal.user_id == user.id,
        )
    ).first()

    if existing:
        db.delete(existing)
    else:
        db.add(PublicSignal(
            user_id=user.id,
            target_type="library",
            target_id=lib_id,
            kind="star",
        ))
    db.commit()


@router.get("/libraries/{lib_id}/comments", response_model=list[CommentEntry])
def get_comments(
    lib_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    lib = _get_public_lib(db, lib_id)

    signals = db.exec(
        select(PublicSignal).where(
            PublicSignal.target_type == "library",
            PublicSignal.target_id == lib.id,
            PublicSignal.kind == "comment",
        )
    ).all()
    signals.sort(key=lambda x: x.created_at)

    return [
        CommentEntry(
            id=s.id,
            username=(db.get(User, s.user_id) or User(username="unknown")).username,
            content=s.content or "",
            created_at=s.created_at,
        )
        for s in signals
    ]


@router.post(
    "/libraries/{lib_id}/comments",
    response_model=CommentEntry,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    lib_id: UUID,
    body: CommentCreate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _get_public_lib(db, lib_id)

    sig = PublicSignal(
        user_id=user.id,
        target_type="library",
        target_id=lib_id,
        kind="comment",
        content=body.content,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)

    return CommentEntry(
        id=sig.id,
        username=user.username,
        content=sig.content or "",
        created_at=sig.created_at,
    )
