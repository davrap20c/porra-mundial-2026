"""
Tests: point calculation and leaderboard.
"""
import json
import pytest
from conftest import open_phase
from models import (db, User, UserScore, GroupPrediction,
                    ActualGroupStanding, KnockoutMatch, KnockoutPrediction,
                    SpecialPrediction, SpecialResult)
from scoring import (calculate_group_points, calculate_knockout_points,
                     calculate_special_points, recalculate_all_scores,
                     get_leaderboard)


def make_user(app, name='TestPlayer'):
    with app.app_context():
        u = User(session_uuid=f'uuid-{name}', name=name, ip='127.0.0.1')
        db.session.add(u)
        db.session.flush()
        db.session.add(UserScore(user_id=u.id, group_points=0,
                                 knockout_points=0, total_points=0))
        db.session.commit()
        return u.id


class TestGroupScoring:
    def test_exact_position_gives_100(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='México', position=1))
            db.session.add(ActualGroupStanding(group_name='A',
                                               team_name='México', position=1))
            db.session.commit()
            assert calculate_group_points(uid) == 100

    def test_wrong_position_gives_0(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='México', position=1))
            db.session.add(ActualGroupStanding(group_name='A',
                                               team_name='México', position=2))
            db.session.commit()
            assert calculate_group_points(uid) == 0

    def test_multiple_hits_accumulate(self, app):
        uid = make_user(app)
        with app.app_context():
            for pos, team in enumerate(['México', 'Corea del Sur',
                                        'Sudáfrica', 'República Checa'], 1):
                db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                               team_name=team, position=pos))
                db.session.add(ActualGroupStanding(group_name='A',
                                                   team_name=team, position=pos))
            db.session.commit()
            assert calculate_group_points(uid) == 400

    def test_no_actuals_gives_0(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='México', position=1))
            db.session.commit()
            assert calculate_group_points(uid) == 0


class TestKnockoutScoring:
    def _setup(self, app, uid, round_id='r32', winner='Brasil'):
        with app.app_context():
            db.session.add(KnockoutMatch(round_id=round_id, match_id=1,
                                         team1='Brasil', team2='Argentina',
                                         winner=winner))
            db.session.add(KnockoutPrediction(user_id=uid, round_id=round_id,
                                              match_id=1, predicted_winner=winner))
            db.session.commit()

    def test_correct_knockout_pick_gives_200(self, app):
        uid = make_user(app)
        self._setup(app, uid)
        with app.app_context():
            assert calculate_knockout_points(uid) == 200

    def test_wrong_knockout_pick_gives_0(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(KnockoutMatch(round_id='r32', match_id=1,
                                         team1='Brasil', team2='Argentina',
                                         winner='Brasil'))
            db.session.add(KnockoutPrediction(user_id=uid, round_id='r32',
                                              match_id=1, predicted_winner='Argentina'))
            db.session.commit()
            assert calculate_knockout_points(uid) == 0

    def test_final_winner_gives_200_plus_300_bonus(self, app):
        uid = make_user(app)
        self._setup(app, uid, round_id='final')
        with app.app_context():
            assert calculate_knockout_points(uid) == 500


class TestSpecialScoring:
    def test_correct_special_gives_500(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(SpecialPrediction(user_id=uid, category='champion',
                                             predicted_value='España'))
            db.session.add(SpecialResult(category='champion', actual_value='España'))
            db.session.commit()
            assert calculate_special_points(uid) == 500

    def test_wrong_special_gives_0(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(SpecialPrediction(user_id=uid, category='champion',
                                             predicted_value='Argentina'))
            db.session.add(SpecialResult(category='champion', actual_value='España'))
            db.session.commit()
            assert calculate_special_points(uid) == 0

    def test_special_comparison_is_case_insensitive(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(SpecialPrediction(user_id=uid, category='top_scorer',
                                             predicted_value='mbappé'))
            db.session.add(SpecialResult(category='top_scorer', actual_value='Mbappé'))
            db.session.commit()
            assert calculate_special_points(uid) == 500

    def test_multiple_specials_accumulate(self, app):
        uid = make_user(app)
        with app.app_context():
            for cat, val in [('champion', 'España'), ('top_scorer', 'Mbappé')]:
                db.session.add(SpecialPrediction(user_id=uid, category=cat,
                                                 predicted_value=val))
                db.session.add(SpecialResult(category=cat, actual_value=val))
            db.session.commit()
            assert calculate_special_points(uid) == 1000

    def test_no_results_gives_0(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(SpecialPrediction(user_id=uid, category='champion',
                                             predicted_value='España'))
            db.session.commit()
            assert calculate_special_points(uid) == 0


class TestLeaderboard:
    def test_leaderboard_ordered_by_total(self, app):
        uid1 = make_user(app, 'Primero')
        uid2 = make_user(app, 'Segundo')
        with app.app_context():
            UserScore.query.filter_by(user_id=uid1).update(
                {'group_points': 200, 'total_points': 200})
            UserScore.query.filter_by(user_id=uid2).update(
                {'group_points': 100, 'total_points': 100})
            db.session.commit()
            board = get_leaderboard()
        assert board[0]['name'] == 'Primero'
        assert board[1]['name'] == 'Segundo'

    def test_recalculate_updates_totals(self, app):
        uid = make_user(app, 'Jugador')
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='México', position=1))
            db.session.add(ActualGroupStanding(group_name='A',
                                               team_name='México', position=1))
            db.session.commit()
            recalculate_all_scores()
            score = UserScore.query.filter_by(user_id=uid).first()
            assert score.group_points == 100
            assert score.total_points == 100

    def test_leaderboard_includes_special_points(self, app):
        uid = make_user(app)
        with app.app_context():
            db.session.add(SpecialPrediction(user_id=uid, category='champion',
                                             predicted_value='España'))
            db.session.add(SpecialResult(category='champion', actual_value='España'))
            db.session.commit()
            recalculate_all_scores()
            board = get_leaderboard()
        assert board[0]['special_points'] == 500
        assert board[0]['total_points'] == 500
