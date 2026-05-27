import json
from datetime import datetime, timedelta, date as date_type

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from database import get_session
from models import User, Library, Line, PracticePosition, ReviewLog, PracticeSession
from auth.dependencies import get_current_user
from schemas.stats import (
    HeatmapResponse,
    HeatmapBucket,
    MasteryResponse,
    MasteryEntry,
    LeechEntry,
    RecentSession,
    TrendPoint,
    LibraryTrendSeries,
    AccuracyTrendResponse,
)

router = APIRouter(prefix="/stats", tags=["stats"])


def _date_bucket(dt: datetime, granularity: str) -> str:
    d = dt.date() if isinstance(dt, datetime) else dt
    if granularity == "weekly":
        return d.strftime("%Y-W%W")
    return d.strftime("%Y-%m-%d")


def _generate_labels(start: date_type, end: date_type, granularity: str) -> list[str]:
    labels, seen, current = [], set(), start
    step = timedelta(days=7 if granularity == "weekly" else 1)
    while current <= end:
        label = _date_bucket(datetime(current.year, current.month, current.day), granularity)
        if label not in seen:
            labels.append(label)
            seen.add(label)
        current += step
    return labels


def _mastery_badge(pct: float, total: int) -> str:
    if total == 0:
        return "not_started"
    if pct < 25:
        return "learning"
    if pct < 50:
        return "developing"
    if pct < 75:
        return "advanced"
    return "mastered"


@router.get("/heatmap", response_model=HeatmapResponse)
def heatmap(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    logs = db.exec(select(ReviewLog).where(ReviewLog.user_id == user.id)).all()

    # Build move_index lookup
    pos_ids = {log.practice_pos_id for log in logs}
    move_index_by_pos: dict = {}
    if pos_ids:
        for pos in db.exec(
            select(PracticePosition).where(PracticePosition.id.in_(pos_ids))
        ).all():
            move_index_by_pos[pos.id] = pos.move_index

    # Aggregate by 1-indexed move number
    buckets: dict[int, dict] = {}
    for log in logs:
        move_index = move_index_by_pos.get(log.practice_pos_id)
        if move_index is None:
            continue
        move_num = move_index + 1
        if move_num not in buckets:
            buckets[move_num] = {"total": 0, "correct": 0}
        buckets[move_num]["total"] += 1
        if log.was_correct:
            buckets[move_num]["correct"] += 1

    result = []
    for move_num in sorted(buckets):
        b = buckets[move_num]
        total = b["total"]
        correct = b["correct"]
        result.append(HeatmapBucket(
            move_number=move_num,
            total=total,
            correct=correct,
            accuracy=round(correct / total, 3) if total > 0 else 0.0,
        ))

    return HeatmapResponse(by_move_number=result)


@router.get("/mastery", response_model=MasteryResponse)
def mastery(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    libraries = db.exec(
        select(Library).where(Library.owner_user_id == user.id)
    ).all()

    result = []
    for lib in libraries:
        lines = db.exec(select(Line).where(Line.library_id == lib.id)).all()
        line_ids = [line.id for line in lines]

        positions = []
        if line_ids:
            positions = db.exec(
                select(PracticePosition).where(
                    PracticePosition.user_id == user.id,
                    PracticePosition.line_id.in_(line_ids),
                )
            ).all()

        total = len(positions)
        mastered = sum(
            1 for p in positions
            if p.repetitions >= 3 and p.ease_factor >= 2.0
        )

        pct = round(mastered / total * 100, 1) if total > 0 else 0.0

        result.append(MasteryEntry(
            library_id=lib.id,
            library_name=lib.name,
            color=lib.color,
            total_positions=total,
            mastered_positions=mastered,
            mastery_pct=pct,
            badge=_mastery_badge(pct, total),
        ))

    # Sort: not_started last, then by mastery desc
    badge_order = {"mastered": 0, "advanced": 1, "developing": 2, "learning": 3, "not_started": 4}
    result.sort(key=lambda x: (badge_order.get(x.badge, 9), -x.mastery_pct))

    return MasteryResponse(libraries=result)


@router.get("/leeches", response_model=list[LeechEntry])
def leeches(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    leech_positions = db.exec(
        select(PracticePosition).where(
            PracticePosition.user_id == user.id,
            PracticePosition.is_leech == True,  # noqa: E712
        )
    ).all()

    result = []
    for pos in leech_positions:
        line = db.get(Line, pos.line_id)
        if not line:
            continue
        lib = db.get(Library, line.library_id)
        if not lib:
            continue
        result.append(LeechEntry(
            practice_position_id=pos.id,
            line_id=pos.line_id,
            line_name=line.name,
            library_id=lib.id,
            library_name=lib.name,
            move_index=pos.move_index,
            leech_count=pos.leech_count,
            ease_factor=pos.ease_factor,
        ))

    result.sort(key=lambda x: x.leech_count, reverse=True)
    return result


@router.get("/recent-sessions", response_model=list[RecentSession])
def recent_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    sessions = db.exec(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(10)
    ).all()

    result = []
    for s in sessions:
        stats = json.loads(s.stats or "{}")
        result.append(RecentSession(
            id=s.id,
            mode=s.mode,
            started_at=s.started_at.isoformat(),
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            correct=stats.get("correct", 0),
            wrong=stats.get("wrong", 0),
            positions_seen=stats.get("positions_seen", 0),
        ))

    return result


@router.get("/accuracy-trend", response_model=AccuracyTrendResponse)
def accuracy_trend(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
    days: int = Query(default=90, ge=0),
    granularity: str = Query(default="daily"),
):
    if granularity not in ("daily", "weekly"):
        granularity = "daily"

    cutoff = None
    if days > 0:
        cutoff = datetime.utcnow() - timedelta(days=days)

    # Fetch all review logs for the user
    query = select(ReviewLog).where(ReviewLog.user_id == user.id)
    if cutoff:
        query = query.where(ReviewLog.reviewed_at >= cutoff)
    logs = db.exec(query).all()

    if not logs:
        return AccuracyTrendResponse(series=[], date_labels=[], granularity=granularity, days=days)

    # Build lookup: pos_id → line_id
    pos_ids = {log.practice_pos_id for log in logs}
    pos_to_line: dict = {}
    for pos in db.exec(select(PracticePosition).where(PracticePosition.id.in_(pos_ids))).all():
        pos_to_line[pos.id] = pos.line_id

    # Build lookup: line_id → library_id
    line_ids = set(pos_to_line.values())
    line_to_lib: dict = {}
    for line in db.exec(select(Line).where(Line.id.in_(line_ids))).all():
        line_to_lib[line.id] = line.library_id

    lib_ids = set(line_to_lib.values())
    lib_info: dict = {}
    for lib in db.exec(select(Library).where(Library.id.in_(lib_ids), Library.owner_user_id == user.id)).all():
        lib_info[lib.id] = lib.name

    # Aggregate: {lib_id: {bucket: {"total": int, "correct": int}}}
    agg: dict = {}
    for log in logs:
        line_id = pos_to_line.get(log.practice_pos_id)
        if not line_id:
            continue
        lib_id = line_to_lib.get(line_id)
        if not lib_id or lib_id not in lib_info:
            continue
        bucket = _date_bucket(log.reviewed_at, granularity)
        if lib_id not in agg:
            agg[lib_id] = {}
        if bucket not in agg[lib_id]:
            agg[lib_id][bucket] = {"total": 0, "correct": 0}
        agg[lib_id][bucket]["total"] += 1
        if log.was_correct:
            agg[lib_id][bucket]["correct"] += 1

    # Generate unified date labels (fills gaps with zeros)
    if not agg:
        return AccuracyTrendResponse(series=[], date_labels=[], granularity=granularity, days=days)

    all_buckets = {b for lib_data in agg.values() for b in lib_data}
    earliest = min(all_buckets)
    try:
        start = datetime.strptime(earliest, "%Y-%m-%d").date() if granularity == "daily" \
            else datetime.strptime(earliest + "-1", "%Y-W%W-%w").date()
    except Exception:
        start = (datetime.utcnow() - timedelta(days=days or 90)).date()
    end = datetime.utcnow().date()
    date_labels = _generate_labels(start, end, granularity)

    # Build series with zero-fill
    series = []
    for lib_id, lib_data in agg.items():
        points = []
        for label in date_labels:
            b = lib_data.get(label, {"total": 0, "correct": 0})
            total, correct = b["total"], b["correct"]
            points.append(TrendPoint(
                date=label,
                total=total,
                correct=correct,
                accuracy=round(correct / total, 3) if total > 0 else 0.0,
            ))
        series.append(LibraryTrendSeries(
            library_id=str(lib_id),
            library_name=lib_info[lib_id],
            points=points,
        ))

    return AccuracyTrendResponse(series=series, date_labels=date_labels, granularity=granularity, days=days)
