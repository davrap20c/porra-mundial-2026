"""
Tests: real-time WebSocket behavior.

socketio.emit() called from HTTP routes (admin/recalcular, admin/phase) goes
through the eventlet transport, which the flask-socketio *test client* does not
intercept.  We therefore split the tests in two layers:

  1. Connection tests — use the SocketIO test client to verify the socket
     handshake and that the connected state is correct.

  2. Emission tests — use unittest.mock.patch to assert that the HTTP route
     calls socketio.emit with the right event name and payload structure.
     This is still an integration test: the full route runs (auth, DB, scoring)
     and we only stub the final transport call.
"""
import pytest
from unittest.mock import patch, ANY
from conftest import open_phase
from main import socketio
from models import db, User, UserScore, GroupPrediction, ActualGroupStanding


def make_user(app, name='RTPlayer'):
    with app.app_context():
        u = User(session_uuid=f'uuid-{name}', name=name, ip='127.0.0.1')
        db.session.add(u)
        db.session.flush()
        db.session.add(UserScore(user_id=u.id, group_points=0,
                                 knockout_points=0, total_points=0))
        db.session.commit()
        return u.id


class TestSocketConnection:
    def test_client_can_connect(self, app, client):
        sc = socketio.test_client(app, flask_test_client=client)
        assert sc.is_connected()
        sc.disconnect()

    def test_disconnect_works(self, app, client):
        sc = socketio.test_client(app, flask_test_client=client)
        sc.disconnect()
        assert not sc.is_connected()

    def test_multiple_clients_connect_independently(self, app):
        c1, c2 = app.test_client(), app.test_client()
        sc1 = socketio.test_client(app, flask_test_client=c1)
        sc2 = socketio.test_client(app, flask_test_client=c2)
        assert sc1.is_connected()
        assert sc2.is_connected()
        sc1.disconnect()
        sc2.disconnect()


class TestScoresUpdatedEmit:
    def test_recalculate_emits_scores_updated(self, app, admin_client):
        make_user(app)
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/recalcular', follow_redirects=True)
            mock_emit.assert_called_once_with('scores_updated', ANY)

    def test_scores_updated_payload_has_leaderboard_list(self, app, admin_client):
        make_user(app, 'Jugador')
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/recalcular', follow_redirects=True)
            _, payload = mock_emit.call_args.args
            assert 'leaderboard' in payload
            assert isinstance(payload['leaderboard'], list)

    def test_leaderboard_payload_has_required_fields(self, app, admin_client):
        make_user(app, 'Campos')
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/recalcular', follow_redirects=True)
            _, payload = mock_emit.call_args.args
            entry = payload['leaderboard'][0]
            for field in ('name', 'rank', 'total_points', 'group_points',
                          'knockout_points', 'special_points'):
                assert field in entry, f'Missing field: {field}'

    def test_recalculate_updates_db_before_emitting(self, app, admin_client):
        uid = make_user(app, 'Scorer')
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='Mexico', position=1))
            db.session.add(ActualGroupStanding(group_name='A',
                                               team_name='Mexico', position=1))
            db.session.commit()

        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/recalcular', follow_redirects=True)
            _, payload = mock_emit.call_args.args
            scorer_entry = next(e for e in payload['leaderboard']
                                if e['name'] == 'Scorer')
            assert scorer_entry['group_points'] == 100
            assert scorer_entry['total_points'] == 100


class TestPhaseUpdatedEmit:
    def test_toggle_phase_emits_phase_updated(self, app, admin_client):
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/phase', data={'key': 'groups_open'},
                              follow_redirects=True)
            mock_emit.assert_called_once_with('phase_updated', ANY)

    def test_phase_updated_payload_contains_all_phase_keys(self, app, admin_client):
        from wc_data import PHASE_CONFIG
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/phase', data={'key': 'r32_open'},
                              follow_redirects=True)
            _, payload = mock_emit.call_args.args
            for key in PHASE_CONFIG:
                assert key in payload, f'Missing phase key: {key}'

    def test_toggle_twice_restores_original_state(self, app, admin_client):
        from models import AppConfig
        with app.app_context():
            before = AppConfig.get('groups_open', 'false')
        admin_client.post('/admin/phase', data={'key': 'groups_open'})
        admin_client.post('/admin/phase', data={'key': 'groups_open'})
        with app.app_context():
            after = AppConfig.get('groups_open', 'false')
        assert before == after


class TestWildcardEmit:
    def test_award_wildcard_emits_event(self, app, admin_client):
        make_user(app, 'TopScorer')
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/comodin', follow_redirects=True)
        emitted_names = [call.args[0] for call in mock_emit.call_args_list]
        assert 'wildcard_awarded' in emitted_names

    def test_wildcard_payload_has_name(self, app, admin_client):
        make_user(app, 'TopScorer')
        with patch.object(socketio, 'emit') as mock_emit:
            admin_client.post('/admin/comodin', follow_redirects=True)
        wc_call = next(c for c in mock_emit.call_args_list
                       if c.args[0] == 'wildcard_awarded')
        assert wc_call.args[1]['name'] == 'TopScorer'
