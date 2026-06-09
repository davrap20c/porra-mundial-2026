from datetime import datetime
from models import db, User, GroupPrediction, KnockoutPrediction, ActualGroupStanding, KnockoutMatch, UserScore, SpecialPrediction, SpecialResult, LeaderboardSnapshot


def calculate_group_points(user_id):
    actuals = {
        (s.group_name, s.team_name): s.position
        for s in ActualGroupStanding.query.all()
    }
    if not actuals:
        return 0

    points = 0
    for pred in GroupPrediction.query.filter_by(user_id=user_id).all():
        actual_pos = actuals.get((pred.group_name, pred.team_name))
        if actual_pos is not None and actual_pos == pred.position:
            points += 100
    return points


def calculate_knockout_points(user_id):
    actuals = {
        (m.round_id, m.match_id): m.winner
        for m in KnockoutMatch.query.filter(KnockoutMatch.winner.isnot(None)).all()
    }
    if not actuals:
        return 0

    points = 0
    for pred in KnockoutPrediction.query.filter_by(user_id=user_id).all():
        winner = actuals.get((pred.round_id, pred.match_id))
        if winner and winner == pred.predicted_winner:
            points += 200
            if pred.round_id == 'final':
                points += 300
    return points


def calculate_special_points(user_id):
    actuals = {r.category: r.actual_value.strip().lower() for r in SpecialResult.query.all()}
    if not actuals:
        return 0
    points = 0
    for pred in SpecialPrediction.query.filter_by(user_id=user_id).all():
        actual = actuals.get(pred.category)
        if actual and actual == pred.predicted_value.strip().lower():
            points += 500
    return points


def recalculate_all_scores():
    for user in User.query.all():
        group_pts = calculate_group_points(user.id)
        knockout_pts = calculate_knockout_points(user.id)
        special_pts = calculate_special_points(user.id)

        score = UserScore.query.filter_by(user_id=user.id).first()
        if not score:
            score = UserScore(user_id=user.id)
            db.session.add(score)

        score.group_points = group_pts
        score.knockout_points = knockout_pts
        score.special_points = special_pts
        score.total_points = group_pts + knockout_pts + special_pts
        score.last_updated = datetime.utcnow()

    db.session.commit()


def get_leaderboard():
    rows = (
        db.session.query(User, UserScore)
        .outerjoin(UserScore, User.id == UserScore.user_id)
        .order_by(
            db.func.coalesce(UserScore.total_points, 0).desc(),
            db.func.coalesce(UserScore.group_points, 0).desc(),  # tiebreaker 1: more group hits
            User.id.asc(),                                        # tiebreaker 2: registered earlier
        )
        .all()
    )
    result = []
    rank = 0
    prev_total = prev_group = None
    for i, (user, score) in enumerate(rows):
        total = score.total_points if score else 0
        grp = score.group_points if score else 0
        if total != prev_total or grp != prev_group:
            rank = i + 1
        prev_total, prev_group = total, grp
        result.append({
            'rank': rank,
            'id': user.id,
            'name': user.name,
            'group_points': grp,
            'knockout_points': score.knockout_points if score else 0,
            'special_points': score.special_points if score else 0,
            'total_points': total,
            'has_wildcard': user.has_wildcard,
            'wildcard_used': user.wildcard_used,
        })
    return result


def save_snapshot(label):
    """Save a leaderboard snapshot after recalculation."""
    for entry in get_leaderboard():
        db.session.add(LeaderboardSnapshot(
            user_id=entry['id'],
            label=label,
            rank=entry['rank'],
            total_points=entry['total_points'],
        ))
    db.session.commit()


def award_wildcard():
    """Award wildcard to the user with the most group stage points."""
    User.query.update({'has_wildcard': False, 'wildcard_used': False})
    db.session.commit()

    top = (
        db.session.query(User, UserScore)
        .outerjoin(UserScore, User.id == UserScore.user_id)
        .order_by(db.func.coalesce(UserScore.group_points, 0).desc())
        .first()
    )
    if top:
        user, score = top
        user.has_wildcard = True
        db.session.commit()
        return user.name
    return None
