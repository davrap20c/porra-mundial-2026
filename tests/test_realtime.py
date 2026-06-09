"""
Tests: real-time WebSocket events via Flask-SocketIO test client.
"""
import json
import pytest
from conftest import open_phase
from main import socketio
from models import (db, User, UserScore, GroupPrediction,
                    ActualGroupStanding)


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


class TestScoresUpdated:
    def test_recalculate_emits_scores_updated(self, app, admin_client):
        uid = make_user(app)
        # Give the user a correct group prediction so recalculate produces data
        with app.app_context():
            db.session.add(GroupPrediction(user_id=uid, group_name='A',
                                           team_name='México', position=1))
            db.session.add(ActualGroupStanding(group_name='A',
                                               team_name='México', position=1))
            db.session.commit()

        sc = socketio.test_client(app, flask_test_client=admin_client)
        sc.get_received()  # flush any connect events

        admin_client.post('/admin/recalcular', follow_redirects=True)

        received = sc.get_received()
        event_names = [e['name'] for e in received]
        assert 'scores_updated' in event_names

    def test_scores_updated_payload_has_leaderboard(self, app, admin_client):
        make_user(app)
        sc = socketio.test_client(app, flask_test_client=admin_client)
        sc.get_received()

        admin_client.post('/admin/recalcular', follow_redirects=True)

        received = sc.get_received()
        scores_event = next(e for e in received if e['name'] == 'scores_updated')
        payload = scores_event['args'][0]
        assert 'leaderboard' in payload
        assert isinstance(payload['leaderboard'], list)

    def test_leaderboard_payload_has_expected_fields(self, app, admin_client):
        make_user(app, 'Campos')
        sc = socketio.test_client(app, flask_test_client=admin_client)
        sc.get_received()

        admin_client.post('/admin/recalcular', follow_redirects=True)

        received = sc.get_received()
        scores_event = next(e for e in received if e['name'] == 'scores_updated')
        entry = scores_event['args'][0]['leaderboard'][0]
        for field in ('name', 'total_points', 'group_points',
                      'knockout_points', 'special_points', 'rank'):
            assert field in entry, f"Missing field: {field}"


class TestPhaseUpdated:
    def test_toggle_phase_emits_phase_updated(self, app, admin_client, client):
        sc = socketio.test_client(app, flask_test_client=client)
        sc.get_received()

        admin_client.post('/admin/phase', data={'key': 'groups_open'},
                          follow_redirects=True)

        received = sc.get_received()
        event_names = [e['name'] for e in received]
        assert 'phase_updated' in event_names

    def test_phase_updated_payload_contains_phase_keys(self, app, admin_client, client):
        sc = socketio.test_client(app, flask_test_client=client)
        sc.get_received()

        admin_client.post('/admin/phase', data={'key': 'groups_open'},
                          follow_redirects=True)

        received = sc.get_received()
        phase_event = next(e for e in received if e['name'] == 'phase_updated')
        payload = phase_event['args'][0]
        assert 'groups_open' in payload
        assert 'specials_open' in payload


class TestMultiClientBroadcast:
    def test_scores_updated_reaches_all_connected_clients(self, app, admin_client):
        """Recalculate should broadcast to every connected socket, not just admin."""
        c1 = app.test_client()
        c2 = app.test_client()
        c1.post('/join', data={'name': 'C1'})
        c2.post('/join', data={'name': 'C2'})

        sc1 = socketio.test_client(app, flask_test_client=c1)
        sc2 = socketio.test_client(app, flask_test_client=c2)
        sc1.get_received()
        sc2.get_received()

        admin_client.post('/admin/recalcular', follow_redirects=True)

        assert any(e['name'] == 'scores_updated' for e in sc1.get_received())
        assert any(e['name'] == 'scores_updated' for e in sc2.get_received())

        sc1.disconnect()
        sc2.disconnect()
