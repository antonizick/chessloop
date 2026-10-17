"""
library_service.py — utilities for managing libraries.
"""

from datetime import datetime
from uuid import UUID
from sqlmodel import Session, select

from models import Library, Line, User
from models.library_video_link import LibraryVideoLink
from models.published_library import PublishedLibrary, PublishedLine
from models.published_library_video_link import PublishedLibraryVideoLink
from sqlalchemy import text


def clone_library_for_user(
    source_library_id: UUID,
    target_user_id: UUID,
    session: Session,
    target_name: str | None = None,
) -> Library:
    """
    Clone a library from one user to another.

    Args:
        source_library_id: ID of the library to clone from
        target_user_id: ID of the user to clone to
        session: Database session
        target_name: Optional custom name for the cloned library. Defaults to source name.

    Returns:
        The newly created cloned library.

    Raises:
        ValueError: If source library not found
    """
    source = session.get(Library, source_library_id)
    if not source:
        raise ValueError(f"Source library {source_library_id} not found")

    # Create new library
    clone_name = target_name or source.name
    cloned = Library(
        name=clone_name,
        color=source.color,
        owner_user_id=target_user_id,
        forked_from_id=source.id,
        description=source.description,
        eco_code=source.eco_code,
        difficulty=source.difficulty,
    )
    session.add(cloned)
    session.flush()  # Ensure cloned.id is set

    # Copy all lines
    for src_line in session.exec(select(Line).where(Line.library_id == source.id)).all():
        session.add(Line(
            library_id=cloned.id,
            name=src_line.name,
            starting_fen=src_line.starting_fen,
            moves=src_line.moves,
            order_index=src_line.order_index,
        ))
    session.flush()

    # Copy all video links
    src_links_stmt = text(
        "SELECT id, title, url FROM library_video_link WHERE library_id = :with_dashes OR library_id = :without_dashes"
    ).bindparams(
        with_dashes=str(source.id),
        without_dashes=str(source.id).replace("-", ""),
    )
    src_links = session.exec(src_links_stmt).all()
    for src_link_row in src_links:
        session.add(LibraryVideoLink(
            library_id=cloned.id,
            title=src_link_row[1],
            url=src_link_row[2],
        ))
    session.flush()

    return cloned


def publish_snapshot(lib: Library, publisher_id: UUID, session: Session) -> PublishedLibrary:
    """Publish a library: store an immutable PublishedLibrary snapshot (with its
    lines and video links) and mark the original public. Commits the session.
    Shared by the publish endpoint and the starter-library seeder."""
    # Create a separate PublishedLibrary snapshot
    published_lib = PublishedLibrary(
        original_library_id=lib.id,
        name=lib.name,
        color=lib.color,
        description=lib.description,
        eco_code=lib.eco_code,
        difficulty=lib.difficulty,
        published_by_user_id=publisher_id,
    )
    session.add(published_lib)
    session.flush()  # Ensure published_lib.id is set

    # Copy all lines
    lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
    for line in lines:
        published_line = PublishedLine(
            published_library_id=published_lib.id,
            original_line_id=line.id,
            name=line.name,
            starting_fen=line.starting_fen,
            moves=line.moves,
            order_index=line.order_index,
        )
        session.add(published_line)
    session.flush()

    # Copy all video links
    vl_stmt = text(
        "SELECT id, title, url FROM library_video_link WHERE library_id = :with_dashes OR library_id = :without_dashes"
    ).bindparams(
        with_dashes=str(lib.id),
        without_dashes=str(lib.id).replace("-", ""),
    )
    video_links = session.exec(vl_stmt).all()
    for vl in video_links:
        pub_vl = PublishedLibraryVideoLink(
            published_library_id=published_lib.id,
            original_video_link_id=UUID(vl[0]) if vl[0] else None,
            title=vl[1],
            url=vl[2],
        )
        session.add(pub_vl)
    session.flush()

    # Mark original library as published (keep for backward compatibility)
    lib.is_public = True
    lib.published_at = datetime.utcnow()
    lib.updated_at = lib.published_at
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return published_lib
