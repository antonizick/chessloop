"""
library_service.py — utilities for managing libraries.
"""

from uuid import UUID
from sqlmodel import Session, select

from models import Library, Line, User
from models.library_video_link import LibraryVideoLink
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
