"""
Tests: admin authentication and protected routes.
"""
import json
import pytest


class TestAdminAuth:
    def test_admin_panel_requires_login(self, client):
        r = client.get('/admin')
        assert r.status_code == 302
        assert 'login' in r.headers['Location']

    def test_wrong_password_denied(self, client):
        r = client.post('/admin/login', data={'password': 'wrong'},
                        follow_redirects=True)
        assert r.status_code == 200
        assert b'incorrecta' in r.data.lower() or b'Incorrecta' in r.data

    def test_correct_password_grants_access(self, client):
        client.post('/admin/login', data={'password': 'testpass'})
        r = client.get('/admin')
        assert r.status_code == 200

    def test_logout_removes_admin_session(self, admin_client):
        admin_client.get('/admin/logout')
        r = admin_client.get('/admin')
        assert r.status_code == 302
        assert 'login' in r.headers['Location']


class TestAdminRoutes:
    def test_toggle_phase_requires_admin(self, client):
        r = client.post('/admin/phase', data={'key': 'groups_open'})
        assert r.status_code == 302
        assert 'login' in r.headers['Location']

    def test_toggle_phase_changes_state(self, admin_client, app):
        from models import AppConfig
        with app.app_context():
            before = AppConfig.get('groups_open', 'false')
        admin_client.post('/admin/phase', data={'key': 'groups_open'})
        with app.app_context():
            after = AppConfig.get('groups_open', 'false')
        assert before != after

    def test_setup_match_requires_admin(self, client):
        r = client.post('/admin/setup-partido',
                        data=json.dumps({'round_id': 'r32', 'match_id': 1,
                                         'team1': 'A', 'team2': 'B'}),
                        content_type='application/json')
        assert r.status_code == 302

    def test_setup_match_creates_match(self, admin_client, app):
        from models import KnockoutMatch
        admin_client.post('/admin/setup-partido',
                          data=json.dumps({'round_id': 'r32', 'match_id': 1,
                                           'team1': 'Brasil', 'team2': 'Argentina'}),
                          content_type='application/json')
        with app.app_context():
            m = KnockoutMatch.query.filter_by(round_id='r32', match_id=1).first()
            assert m is not None
            assert m.team1 == 'Brasil'

    def test_match_result_requires_valid_team(self, admin_client, app):
        admin_client.post('/admin/setup-partido',
                          data=json.dumps({'round_id': 'r32', 'match_id': 1,
                                           'team1': 'Brasil', 'team2': 'Argentina'}),
                          content_type='application/json')
        r = admin_client.post('/admin/resultado-partido',
                              data=json.dumps({'round_id': 'r32', 'match_id': 1,
                                               'winner': 'Inventado FC'}),
                              content_type='application/json')
        assert r.status_code == 400

    def test_group_result_requires_4_teams(self, admin_client):
        r = admin_client.post('/admin/resultados-grupos',
                              data=json.dumps({'group': 'A', 'teams': ['México', 'Brasil']}),
                              content_type='application/json')
        assert r.status_code == 400

    def test_special_result_invalid_category_rejected(self, admin_client):
        r = admin_client.post('/admin/resultado-especial',
                              data=json.dumps({'category': 'fake_cat', 'value': 'x'}),
                              content_type='application/json')
        assert r.status_code == 400
