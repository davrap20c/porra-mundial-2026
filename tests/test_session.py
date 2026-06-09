"""
Tests: one user per session (device).

The app enforces one identity per browser session via a signed cookie.
A fresh client (no cookie) can always create a new user — that's intentional
so different people on different devices can each join. The protection tested
here is that the SAME browser session cannot create a second user.
"""
import pytest
from conftest import open_phase
from models import User


class TestJoin:
    def test_join_creates_user(self, client, app):
        r = client.post('/join', data={'name': 'Ana'}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert User.query.filter_by(name='Ana').count() == 1

    def test_join_stores_session(self, client, app):
        client.post('/join', data={'name': 'Ana'})
        # Session is set — subsequent visit to / shows logged-in state
        r = client.get('/')
        assert r.status_code == 200

    def test_empty_name_rejected(self, client, app):
        r = client.post('/join', data={'name': ''}, follow_redirects=True)
        with app.app_context():
            assert User.query.count() == 0

    def test_long_name_rejected(self, client, app):
        r = client.post('/join', data={'name': 'A' * 31}, follow_redirects=True)
        with app.app_context():
            assert User.query.count() == 0

    def test_join_redirects_to_index_on_success(self, client):
        r = client.post('/join', data={'name': 'Ana'})
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/')


class TestOneUserPerSession:
    def test_same_session_cannot_join_twice(self, client, app):
        """Core device-restriction test: once you have a session, /join bounces you."""
        client.post('/join', data={'name': 'Primera'})
        # Try to register a second identity in the same browser session
        r = client.post('/join', data={'name': 'Segunda'}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            # Only one user must exist
            assert User.query.count() == 1
            assert User.query.filter_by(name='Segunda').count() == 0

    def test_same_session_get_join_redirects_to_index(self, client):
        """Visiting /join when already logged in redirects home, not a new form."""
        client.post('/join', data={'name': 'Primera'})
        r = client.get('/join')
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/')

    def test_different_sessions_create_separate_users(self, app):
        """Two different browsers/devices can each register independently."""
        c1 = app.test_client()
        c2 = app.test_client()
        c1.post('/join', data={'name': 'Jugador1'})
        c2.post('/join', data={'name': 'Jugador2'})
        with app.app_context():
            assert User.query.count() == 2
            assert User.query.filter_by(name='Jugador1').count() == 1
            assert User.query.filter_by(name='Jugador2').count() == 1

    def test_logout_clears_session(self, client, app):
        """After logout, the same client is treated as a new visitor."""
        client.post('/join', data={'name': 'Antes'})
        client.get('/salir')
        # Now the join page should be accessible again (not redirected)
        r = client.get('/join')
        assert r.status_code == 200

    def test_logout_then_rejoin_creates_new_user(self, client, app):
        client.post('/join', data={'name': 'PrimerNombre'})
        client.get('/salir')
        client.post('/join', data={'name': 'SegundoNombre'})
        with app.app_context():
            # Both users exist in DB — old one persists, new one created
            assert User.query.count() == 2
