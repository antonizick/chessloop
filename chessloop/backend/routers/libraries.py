from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database import get_session
from models import User, Library, Line
from auth.dependencies import get_current_user
from schemas.library import (
    LibraryCreate,
    LibraryUpdate,
    LibraryActiveToggle,
    LibraryResponse,
)

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _owned_or_404(session: Session, lib_id: UUID, user: User) -> Library:
    lib = session.get(Library, lib_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if lib.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
    return lib


@router.get("", response_model=list[LibraryResponse])
def list_libraries(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(Library).where(Library.owner_user_id == user.id)).all()


@router.post("", response_model=LibraryResponse, status_code=status.HTTP_201_CREATED)
def create_library(
    body: LibraryCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = Library(owner_user_id=user.id, **body.model_dump())
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.get("/{lib_id}", response_model=LibraryResponse)
def get_library(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _owned_or_404(session, lib_id, user)


@router.put("/{lib_id}", response_model=LibraryResponse)
def update_library(
    lib_id: UUID,
    body: LibraryUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)

    # If renaming, check for duplicates first
    if "name" in body.model_dump(exclude_unset=True):
        new_name = body.name
        existing = session.exec(
            select(Library).where(
                Library.owner_user_id == user.id,
                Library.name == new_name,
                Library.id != lib_id,
            )
        ).first()
        if existing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Library name '{new_name}' already exists in your account"
            )

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(lib, k, v)
    lib.updated_at = datetime.utcnow()
    session.add(lib)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        if "uq_owner_library_name" in str(e):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Library name '{lib.name}' already exists in your account"
            )
        raise
    session.refresh(lib)
    return lib


@router.delete("/{lib_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)
    for line in session.exec(select(Line).where(Line.library_id == lib.id)).all():
        session.delete(line)
    session.flush()  # ensure child rows are gone before deleting the parent under FK
    session.delete(lib)
    session.commit()


@router.patch("/{lib_id}/active", response_model=LibraryResponse)
def set_active(
    lib_id: UUID,
    body: LibraryActiveToggle,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)
    lib.is_active = body.is_active
    lib.updated_at = datetime.utcnow()
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.post("/{lib_id}/publish", response_model=LibraryResponse)
def publish(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)
    lib.is_public = True
    lib.published_at = datetime.utcnow()
    lib.updated_at = lib.published_at
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.post("/{lib_id}/fork", response_model=LibraryResponse, status_code=status.HTTP_201_CREATED)
def fork(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    source = session.get(Library, lib_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if not source.is_public and source.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Library is private")

    forked = Library(
        name=f"{source.name} (fork)",
        color=source.color,
        owner_user_id=user.id,
        forked_from_id=source.id,
        description=source.description,
        eco_code=source.eco_code,
        difficulty=source.difficulty,
    )
    session.add(forked)
    session.commit()
    session.refresh(forked)

    for src_line in session.exec(select(Line).where(Line.library_id == source.id)).all():
        session.add(Line(
            library_id=forked.id,
            name=src_line.name,
            starting_fen=src_line.starting_fen,
            moves=src_line.moves,
            order_index=src_line.order_index,
        ))
    session.commit()
    return forked
