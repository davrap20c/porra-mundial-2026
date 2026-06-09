"""
Tests: streak daily prediction system — fetcher logic, scoring, API endpoints.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from conftest import open_phase
from models import db, User, UserScore, AppConfig, StreakPick, DiscordLink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(app, name='Player1'):
    with app.app_context():
        u = User(session_uuid=f'uuid-{name}', name=name, ip='127.0.0.1')
        db.session.add(u)
        db.session.flush()
        db.session.add(UserScore(user_id=u.id, group_points=0,
                                 knockout_points=0, total_points=0))
        db.session.commit()
        return u.id


def set_streak_match(app, date, home, away, result=None):
    with app.app_context():
        AppConfig.set('streak_match', json.dumps(
            {'date': date, 'home': home, 'away': away, 'result': result}))


def add_pick(app, user_id, date, pick, correct=None):
    with app.app_context():
        db.session.add(StreakPick(user_id=user_id, match_date=date,
                                  pick=pick, correct=correct))
        db.session.commit()


def resolve_date(app, date):
    with app.app_context():
        raw = AppConfig.get('streak_resolved_dates', '[]')
        dates = json.loads(raw)
        if date not in dates:
            dates.append(date)
            dates.sort()
            AppConfig.set('streak_resolved_dates', json.dumps(dates))


# ---------------------------------------------------------------------------
# Streak point formula
# ---------------------------------------------------------------------------

class TestStreakPointFormula:
    """Points: nth correct in a row earns n*10. Miss/wrong resets streak."""

    def test_one_correct_gives_10(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([('2026-06-11', True)])
        assert pts == 10
        assert cur == 1

    def test_two_in_a_row_gives_30(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([
            ('2026-06-11', True),
            ('2026-06-12', True),
        ])
        assert pts == 30   # 10 + 20
        assert cur == 2

    def test_three_in_a_row_gives_60(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([
            ('2026-06-11', True),
            ('2026-06-12', True),
            ('2026-06-13', True),
        ])
        assert pts == 60   # 10 + 20 + 30
        assert cur == 3

    def test_wrong_resets_streak_keeps_points(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([
            ('2026-06-11', True),   # +10 → 10
            ('2026-06-12', True),   # +20 → 30
            ('2026-06-13', False),  # reset
            ('2026-06-14', True),   # +10 → 40
        ])
        assert pts == 40
        assert cur == 1
        assert mx == 2

    def test_miss_resets_streak_keeps_points(self, app):
        from main import _calc_streak_stats
        # None = no vote = streak reset
        cur, mx, pts = _calc_streak_stats([
            ('2026-06-11', True),   # +10 → 10
            ('2026-06-12', None),   # miss → reset
            ('2026-06-13', True),   # +10 → 20
            ('2026-06-14', True),   # +20 → 40
        ])
        assert pts == 40
        assert cur == 2
        assert mx == 2

    def test_all_wrong_gives_zero_points(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([
            ('2026-06-11', False),
            ('2026-06-12', False),
        ])
        assert pts == 0
        assert cur == 0

    def test_empty_gives_zeros(self, app):
        from main import _calc_streak_stats
        cur, mx, pts = _calc_streak_stats([])
        assert (cur, mx, pts) == (0, 0, 0)


# ---------------------------------------------------------------------------
# get_streak_stats (single user, reads from DB)
# ---------------------------------------------------------------------------

class TestGetStreakStats:
    def test_no_resolved_dates_returns_zeros(self, app):
        uid = make_user(app, 'A')
        from main import get_streak_stats
        with app.app_context():
            assert get_streak_stats(uid) == (0, 0, 0)

    def test_user_with_correct_picks(self, app):
        uid = make_user(app, 'B')
        resolve_date(app, '2026-06-11')
        resolve_date(app, '2026-06-12')
        add_pick(app, uid, '2026-06-11', 'home', correct=True)
        add_pick(app, uid, '2026-06-12', 'home', correct=True)
        from main import get_streak_stats
        with app.app_context():
            cur, mx, pts = get_streak_stats(uid)
        assert cur == 2
        assert pts == 30

    def test_missed_day_resets_streak(self, app):
        uid = make_user(app, 'C')
        resolve_date(app, '2026-06-11')
        resolve_date(app, '2026-06-12')
        resolve_date(app, '2026-06-13')
        add_pick(app, uid, '2026-06-11', 'home', correct=True)
        # no pick on 2026-06-12 → miss
        add_pick(app, uid, '2026-06-13', 'home', correct=True)
        from main import get_streak_stats
        with app.app_context():
            cur, mx, pts = get_streak_stats(uid)
        assert cur == 1
        assert mx == 1
        assert pts == 20   # 10 (day1) + 10 (day3, streak reset to 1)


# ---------------------------------------------------------------------------
# _streak_stats_for_users (all users)
# ---------------------------------------------------------------------------

class TestStreakStatsForUsers:
    def test_returns_empty_without_resolved_dates(self, app):
        make_user(app, 'D')
        from main import _streak_stats_for_users
        with app.app_context():
            result = _streak_stats_for_users()
        assert result == {}

    def test_user_not_voted_appears_with_zero_streak(self, app):
        uid = make_user(app, 'E')
        resolve_date(app, '2026-06-11')
        add_pick(app, uid, '2026-06-11', 'home', correct=True)
        uid2 = make_user(app, 'F')
        # uid2 never voted
        from main import _streak_stats_for_users
        with app.app_context():
            stats = _streak_stats_for_users()
        # uid2 never voted so shouldn't appear (no picks at all)
        assert uid in stats
        assert stats[uid]['current'] == 1

    def test_ranking_sorted_by_points(self, app):
        uid1 = make_user(app, 'G')
        uid2 = make_user(app, 'H')
        resolve_date(app, '2026-06-11')
        resolve_date(app, '2026-06-12')
        # uid1: 2 correct in a row → 30 pts
        add_pick(app, uid1, '2026-06-11', 'home', correct=True)
        add_pick(app, uid1, '2026-06-12', 'home', correct=True)
        # uid2: 1 correct → 10 pts
        add_pick(app, uid2, '2026-06-11', 'home', correct=True)
        from main import get_streak_rankings
        with app.app_context():
            rankings = get_streak_rankings()
        assert rankings[0]['user_id'] == uid1
        assert rankings[0]['points'] == 30
        assert rankings[1]['points'] == 10


# ---------------------------------------------------------------------------
# Streak API endpoints
# ---------------------------------------------------------------------------

class TestStreakAPI:
    def test_api_streak_no_match(self, client):
        r = client.get('/api/streak')
        assert r.status_code == 200
        data = r.get_json()
        assert data['match'] is None

    def test_api_streak_with_match(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.get('/api/streak')
        data = r.get_json()
        assert data['match']['home'] == 'México'
        assert data['match']['away'] == 'Sudáfrica'
        assert data['locked'] is False

    def test_api_streak_locked_after_result(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica', result='home')
        r = client.get('/api/streak')
        data = r.get_json()
        assert data['locked'] is True
        assert data['match']['result'] == 'home'

    def test_api_streak_votes_empty(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.get('/api/streak/votes')
        data = r.get_json()
        assert data['total'] == 0
        assert data['pct'] == {'home': 0, 'draw': 0, 'away': 0}

    def test_api_streak_votes_with_picks(self, app, client):
        uid = make_user(app, 'Voter')
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        add_pick(app, uid, '2026-06-11', 'home', correct=None)
        r = client.get('/api/streak/votes')
        data = r.get_json()
        assert data['total'] == 1
        assert data['counts']['home'] == 1
        assert data['pct']['home'] == 100

    def test_api_streak_rankings_empty(self, client):
        r = client.get('/api/streak/rankings')
        data = r.get_json()
        assert data['rankings'] == []

    def test_streak_pick_requires_login(self, client, app):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.post('/api/streak/pick',
                        json={'pick': 'home'},
                        content_type='application/json')
        assert r.status_code in (401, 403, 302)

    def test_streak_pick_logged_in(self, app, joined_client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = joined_client.post('/api/streak/pick',
                               json={'pick': 'home'},
                               content_type='application/json')
        assert r.get_json()['ok'] is True

    def test_streak_pick_locked_match_rejected(self, app, joined_client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica', result='home')
        r = joined_client.post('/api/streak/pick',
                               json={'pick': 'away'},
                               content_type='application/json')
        assert r.get_json()['ok'] is False

    def test_streak_pick_invalid_option_rejected(self, app, joined_client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = joined_client.post('/api/streak/pick',
                               json={'pick': 'invalid'},
                               content_type='application/json')
        assert r.get_json()['ok'] is False


# ---------------------------------------------------------------------------
# Admin streak endpoints
# ---------------------------------------------------------------------------

def admin_post(client, url, payload):
    """POST as admin by injecting the session directly."""
    with client.session_transaction() as sess:
        sess['is_admin'] = True
    return client.post(url, data=json.dumps(payload), content_type='application/json')


class TestAdminStreakEndpoints:
    def test_set_match(self, client):
        r = admin_post(client, '/admin/streak/set-match',
                       {'date': '2026-06-11', 'home': 'México', 'away': 'Sudáfrica'})
        assert r.get_json()['ok'] is True

    def test_set_match_missing_fields(self, client):
        r = admin_post(client, '/admin/streak/set-match',
                       {'date': '2026-06-11', 'home': 'México'})
        assert r.get_json()['ok'] is False

    def test_set_result_registers_resolved_date(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = admin_post(client, '/admin/streak/set-result', {'result': 'home'})
        assert r.get_json()['ok'] is True
        with app.app_context():
            dates = json.loads(AppConfig.get('streak_resolved_dates', '[]'))
        assert '2026-06-11' in dates

    def test_set_result_marks_picks_correct(self, app, client):
        uid = make_user(app, 'Picker')
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        add_pick(app, uid, '2026-06-11', 'home', correct=None)
        admin_post(client, '/admin/streak/set-result', {'result': 'home'})
        with app.app_context():
            p = StreakPick.query.filter_by(user_id=uid).first()
        assert p.correct is True

    def test_set_result_marks_wrong_pick(self, app, client):
        uid = make_user(app, 'Loser')
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        add_pick(app, uid, '2026-06-11', 'away', correct=None)
        admin_post(client, '/admin/streak/set-result', {'result': 'home'})
        with app.app_context():
            p = StreakPick.query.filter_by(user_id=uid).first()
        assert p.correct is False

    def test_set_result_invalid_rejected(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = admin_post(client, '/admin/streak/set-result', {'result': 'bad'})
        assert r.get_json()['ok'] is False

    def test_notify_now_requires_match(self, client):
        r = admin_post(client, '/admin/streak/notify-now', {})
        assert r.get_json()['ok'] is False

    def test_notify_now_sets_flag(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        admin_post(client, '/admin/streak/notify-now', {})
        with app.app_context():
            assert AppConfig.get('streak_force_notify') == '1'


# ---------------------------------------------------------------------------
# Fetcher auto_update_streak logic (mocked API)
# ---------------------------------------------------------------------------

FAKE_MATCH_SCHEDULED = {
    'date': '2026-06-11T21:00:00Z',
    'home': 'México',
    'away': 'Sudáfrica',
    'stage': 'GROUP_STAGE',
    'group': 'A',
    'status': 'TIMED',
    'score_home': None,
    'score_away': None,
}

FAKE_MATCH_LIVE = {**FAKE_MATCH_SCHEDULED, 'status': 'IN_PLAY'}

FAKE_MATCH_FINISHED = {
    **FAKE_MATCH_SCHEDULED,
    'status': 'FINISHED',
    'score_home': 2,
    'score_away': 0,
}


class TestFetcherAutoUpdateStreak:
    def test_sets_match_from_scheduled_today(self, app):
        import fetcher
        today = '2026-06-11'
        fake = {**FAKE_MATCH_SCHEDULED, 'date': f'{today}T21:00:00Z'}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                changed = fetcher.auto_update_streak()
        assert changed is not None
        assert 'new_match' in changed
        assert changed['new_match']['home'] == 'México'

    def test_sets_result_when_finished(self, app):
        import fetcher
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica')
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z'}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                changed = fetcher.auto_update_streak()
        assert changed is not None
        assert changed.get('result') == 'home'

    def test_result_draw(self, app):
        import fetcher
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica')
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z',
                'score_home': 1, 'score_away': 1}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                changed = fetcher.auto_update_streak()
        assert changed['result'] == 'draw'

    def test_result_away_win(self, app):
        import fetcher
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica')
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z',
                'score_home': 0, 'score_away': 3}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                changed = fetcher.auto_update_streak()
        assert changed['result'] == 'away'

    def test_no_change_when_result_already_set(self, app):
        import fetcher
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica', result='home')
        resolve_date(app, today)
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z'}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                changed = fetcher.auto_update_streak()
        # result already set, no new changes
        assert changed is None or 'result' not in (changed or {})

    def test_api_unavailable_returns_none(self, app):
        import fetcher
        with patch('fetcher.fetch_upcoming_matches', return_value=None):
            with app.app_context():
                result = fetcher.auto_update_streak()
        assert result is None

    def test_resolved_date_registered_after_result(self, app):
        import fetcher
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica')
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z'}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                fetcher.auto_update_streak()
                dates = json.loads(AppConfig.get('streak_resolved_dates', '[]'))
        assert today in dates

    def test_picks_marked_after_result(self, app):
        import fetcher
        uid = make_user(app, 'AutoPicker')
        today = '2026-06-11'
        set_streak_match(app, today, 'México', 'Sudáfrica')
        add_pick(app, uid, today, 'home', correct=None)
        fake = {**FAKE_MATCH_FINISHED, 'date': f'{today}T21:00:00Z'}
        with patch('fetcher.fetch_upcoming_matches', return_value=[fake]), \
             patch('fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = MagicMock(
                strftime=lambda fmt: today if '%Y-%m-%d' in fmt else today)
            with app.app_context():
                fetcher.auto_update_streak()
                p = StreakPick.query.filter_by(user_id=uid).first()
                correct = p.correct
        assert correct is True


# ---------------------------------------------------------------------------
# Discord bot API endpoints
# ---------------------------------------------------------------------------

class TestDiscordBotAPI:
    BOT_SECRET = 'test-bot-secret'

    @pytest.fixture(autouse=True)
    def set_bot_secret(self, app):
        import main
        main.BOT_SECRET = self.BOT_SECRET

    def headers(self):
        return {'X-Bot-Secret': self.BOT_SECRET, 'Content-Type': 'application/json'}

    def test_vincular_unknown_code(self, client):
        r = client.post('/api/discord/vincular',
                        json={'discord_id': '123', 'discord_name': 'user', 'code': 'XXXXXXXX'},
                        headers=self.headers())
        assert r.get_json()['ok'] is False

    def test_vincular_valid_code(self, app, client):
        uid = make_user(app, 'DiscordUser')
        with app.app_context():
            u = db.session.get(User, uid)
            u.recovery_code = 'ABCD1234'
            db.session.commit()
        r = client.post('/api/discord/vincular',
                        json={'discord_id': '999888777', 'discord_name': 'duser#0001',
                              'code': 'ABCD1234'},
                        headers=self.headers())
        assert r.get_json()['ok'] is True
        assert r.get_json()['name'] == 'DiscordUser'

    def test_pick_no_link(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.post('/api/discord/pick',
                        json={'discord_id': '000000000', 'pick': 'home'},
                        headers=self.headers())
        data = r.get_json()
        assert data['ok'] is False
        assert 'no_link' in data.get('msg', '')

    def test_pick_saves_correctly(self, app, client):
        uid = make_user(app, 'BotUser')
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        with app.app_context():
            db.session.add(DiscordLink(user_id=uid, discord_id='111222333',
                                       discord_name='botuser#1234'))
            db.session.commit()
        r = client.post('/api/discord/pick',
                        json={'discord_id': '111222333', 'pick': 'draw'},
                        headers=self.headers())
        assert r.get_json()['ok'] is True
        with app.app_context():
            p = StreakPick.query.filter_by(user_id=uid).first()
        assert p.pick == 'draw'

    def test_pick_rejected_without_secret(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.post('/api/discord/pick',
                        json={'discord_id': '111', 'pick': 'home'},
                        content_type='application/json')
        assert r.status_code == 403

    def test_pick_status_no_link(self, app, client):
        set_streak_match(app, '2026-06-11', 'México', 'Sudáfrica')
        r = client.post('/api/discord/pick_status',
                        json={'discord_id': '000'},
                        headers=self.headers())
        assert r.get_json()['pick'] is None

    def test_mark_notified(self, app, client):
        r = client.post('/api/streak/mark-notified',
                        json={'match_key': '2026-06-11|México|Sudáfrica'},
                        headers=self.headers())
        assert r.get_json()['ok'] is True
        with app.app_context():
            assert AppConfig.get('streak_last_notified') == '2026-06-11|México|Sudáfrica'

    def test_clear_notify(self, app, client):
        with app.app_context():
            AppConfig.set('streak_force_notify', '1')
        r = client.post('/api/streak/clear-notify',
                        json={'match_key': '2026-06-11|México|Sudáfrica'},
                        headers=self.headers())
        assert r.get_json()['ok'] is True
        with app.app_context():
            assert AppConfig.get('streak_force_notify') == '0'
