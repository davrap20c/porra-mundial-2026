from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    session_uuid = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    has_wildcard = db.Column(db.Boolean, default=False)
    wildcard_used = db.Column(db.Boolean, default=False)
    recovery_code = db.Column(db.String(10), unique=True, nullable=True)

    score = db.relationship('UserScore', backref='user', uselist=False, cascade='all, delete-orphan')
    group_predictions = db.relationship('GroupPrediction', backref='user', cascade='all, delete-orphan')
    knockout_predictions = db.relationship('KnockoutPrediction', backref='user', cascade='all, delete-orphan')


class GroupPrediction(db.Model):
    __tablename__ = 'group_predictions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_name = db.Column(db.String(2), nullable=False)
    team_name = db.Column(db.String(60), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'group_name', 'team_name'),)


class KnockoutPrediction(db.Model):
    __tablename__ = 'knockout_predictions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    round_id = db.Column(db.String(10), nullable=False)
    match_id = db.Column(db.Integer, nullable=False)
    predicted_winner = db.Column(db.String(60), nullable=False)
    is_wildcard = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'round_id', 'match_id'),)


class ActualGroupStanding(db.Model):
    __tablename__ = 'actual_group_standings'
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(2), nullable=False)
    team_name = db.Column(db.String(60), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('group_name', 'team_name'),)


class KnockoutMatch(db.Model):
    __tablename__ = 'knockout_matches'
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.String(10), nullable=False)
    match_id = db.Column(db.Integer, nullable=False)
    team1 = db.Column(db.String(60), nullable=False)
    team2 = db.Column(db.String(60), nullable=False)
    winner = db.Column(db.String(60))
    __table_args__ = (db.UniqueConstraint('round_id', 'match_id'),)


class AppConfig(db.Model):
    __tablename__ = 'app_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), unique=True, nullable=False)
    value = db.Column(db.Text, default='')

    @classmethod
    def get(cls, key, default=''):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = str(value)
        else:
            db.session.add(cls(key=key, value=str(value)))
        db.session.commit()


class SpecialPrediction(db.Model):
    __tablename__ = 'special_predictions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    predicted_value = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'category'),)


class SpecialResult(db.Model):
    __tablename__ = 'special_results'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(30), unique=True, nullable=False)
    actual_value = db.Column(db.String(100), nullable=False)


class UserScore(db.Model):
    __tablename__ = 'user_scores'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    group_points = db.Column(db.Integer, default=0)
    knockout_points = db.Column(db.Integer, default=0)
    special_points = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime)


class LeaderboardSnapshot(db.Model):
    __tablename__ = 'leaderboard_snapshots'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    label = db.Column(db.String(60), nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    total_points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DiscordLink(db.Model):
    __tablename__ = 'discord_links'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    discord_id  = db.Column(db.String(30), unique=True, nullable=False)
    discord_name = db.Column(db.String(100))
    linked_at   = db.Column(db.DateTime, default=datetime.utcnow)


class StreakPick(db.Model):
    __tablename__ = 'streak_picks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    match_date = db.Column(db.String(50), nullable=False)  # full ISO date string from API
    pick = db.Column(db.String(10), nullable=False)        # 'home' | 'draw' | 'away'
    correct = db.Column(db.Boolean)                        # None until admin enters result
    __table_args__ = (db.UniqueConstraint('user_id', 'match_date'),)
