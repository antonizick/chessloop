from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from database import get_session
from models import User, Library, Line
from models.public_signal import PublicSignal
from models.library_video_link import LibraryVideoLink
from models.published_library import PublishedLibrary, PublishedLine
from models.published_library_video_link import PublishedLibraryVideoLink
from auth.dependencies import get_current_user
from schemas.public import (
    PublicLibraryEntry,
    PublicLibraryDetail,
    CommentEntry,
    CommentCreate,
)
from schemas.library_video_link import VideoLinkResponse
from schemas.line import LineResponse

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
    return len(db.exec(select(PublishedLine).where(PublishedLine.published_library_id == library_id)).all())


def _get_public_lib(db: Session, lib_id: UUID) -> PublishedLibrary:
    lib = db.get(PublishedLibrary, lib_id)
    if not lib:
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
    stmt = select(PublishedLibrary)
    if q:
        stmt = stmt.where(PublishedLibrary.name.contains(q))
    if eco:
        stmt = stmt.where(PublishedLibrary.eco_code == eco.upper())
    if color and color in ("white", "black", "both"):
        stmt = stmt.where(PublishedLibrary.color == color)
    if difficulty and difficulty in ("beginner", "intermediate", "advanced"):
        stmt = stmt.where(PublishedLibrary.difficulty == difficulty)

    libraries = db.exec(stmt).all()

    result = []
    from sqlalchemy import text
    for lib in libraries:
        # Get original owner from original library
        owner_user_id = lib.published_by_user_id
        if lib.original_library_id:
            original = db.get(Library, lib.original_library_id)
            if original:
                owner_user_id = original.owner_user_id

        owner = db.get(User, owner_user_id) if owner_user_id else None

        # Get video links from published library
        video_links = db.exec(
            select(PublishedLibraryVideoLink).where(
                PublishedLibraryVideoLink.published_library_id == lib.id
            ).order_by(PublishedLibraryVideoLink.created_at)
        ).all()

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
            forked_from_id=None,  # Published libraries don't have fork relationships
            video_links=[VideoLinkResponse(id=vl.id, library_id=lib.id, title=vl.title, url=vl.url, created_at=vl.created_at) for vl in video_links],
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

    # Get original owner from original library
    owner_user_id = lib.published_by_user_id
    if lib.original_library_id:
        original = db.get(Library, lib.original_library_id)
        if original:
            owner_user_id = original.owner_user_id

    owner = db.get(User, owner_user_id) if owner_user_id else None

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

    video_links = db.exec(
        select(PublishedLibraryVideoLink).where(
            PublishedLibraryVideoLink.published_library_id == lib.id
        ).order_by(PublishedLibraryVideoLink.created_at)
    ).all()

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
        forked_from_id=None,
        user_has_starred=user_starred,
        comments=comments,
        video_links=[VideoLinkResponse(id=vl.id, library_id=lib.id, title=vl.title, url=vl.url, created_at=vl.created_at) for vl in video_links],
    )


@router.get("/libraries/{lib_id}/lines", response_model=list[LineResponse])
def get_public_library_lines(
    lib_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    lib = _get_public_lib(db, lib_id)
    published_lines = db.exec(
        select(PublishedLine).where(PublishedLine.published_library_id == lib.id).order_by(PublishedLine.order_index)
    ).all()
    # Convert PublishedLine to LineResponse format
    return [
        LineResponse(
            id=pl.id,
            library_id=lib.id,
            name=pl.name,
            starting_fen=pl.starting_fen,
            moves=pl.moves,
            order_index=pl.order_index,
            created_at=pl.created_at,
            updated_at=pl.created_at,
        )
        for pl in published_lines
    ]


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


@router.post("/libraries/{lib_id}/fork", status_code=status.HTTP_201_CREATED)
def fork_published_library(
    lib_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Fork a published library into the user's personal libraries."""
    from schemas.library import LibraryResponse

    pub_lib = _get_public_lib(db, lib_id)

    # Create new personal library from published library
    from models import Library
    forked = Library(
        name=f"{pub_lib.name} (fork)",
        color=pub_lib.color,
        owner_user_id=user.id,
        description=pub_lib.description,
        eco_code=pub_lib.eco_code,
        difficulty=pub_lib.difficulty,
    )
    db.add(forked)
    db.flush()

    # Copy all published lines to personal library
    published_lines = db.exec(
        select(PublishedLine).where(PublishedLine.published_library_id == pub_lib.id).order_by(PublishedLine.order_index)
    ).all()
    for pub_line in published_lines:
        db.add(Line(
            library_id=forked.id,
            name=pub_line.name,
            starting_fen=pub_line.starting_fen,
            moves=pub_line.moves,
            order_index=pub_line.order_index,
        ))
    db.flush()

    # Copy all published video links
    pub_video_links = db.exec(
        select(PublishedLibraryVideoLink).where(PublishedLibraryVideoLink.published_library_id == pub_lib.id)
    ).all()
    for pub_vl in pub_video_links:
        db.add(LibraryVideoLink(
            library_id=forked.id,
            title=pub_vl.title,
            url=pub_vl.url,
        ))
    db.flush()

    db.commit()
    db.refresh(forked)

    from services.activity_log import log_activity
    log_activity(db, user.id, user.username, "fork_library", target=pub_lib.name, detail=f"→ {forked.name}")

    return LibraryResponse(
        id=forked.id,
        name=forked.name,
        color=forked.color,
        owner_user_id=forked.owner_user_id,
        is_active=forked.is_active,
        is_public=forked.is_public,
        published_at=forked.published_at,
        description=forked.description,
        eco_code=forked.eco_code,
        difficulty=forked.difficulty,
        created_at=forked.created_at,
        updated_at=forked.updated_at,
    )
