"""
Tests: group, knockout and special predictions.
"""
import json
import pytest
from conftest import open_phase, close_phase
from wc_data import DEFAULT_GROUPS


VALID_GROUPS = {
    group: list(teams) for group, teams in DEFAULT_GROUPS.items()
}


class TestGroupPredictions:
    def test_groups_closed_by_default_returns_403(self, joined_client):
        r = joined_client.post(
            '/predicciones/grupos',
            data=json.dumps(VALID_GROUPS),
            content_type='application/json',
        )
        assert r.status_code == 403
        assert json.loads(r.data)['ok'] is False

    def test_groups_open_allows_save(self, joined_client, app):
        open_phase(app, 'groups_open')
        r = joined_client.post(
            '/predicciones/grupos',
            data=json.dumps(VALID_GROUPS),
            content_type='application/json',
        )
        data = json.loads(r.data)
        assert r.status_code == 200
        assert data['ok'] is True

    def test_groups_prediction_persists(self, joined_client, app):
        open_phase(app, 'groups_open')
        joined_client.post(
            '/predicciones/grupos',
            data=json.dumps(VALID_GROUPS),
            content_type='application/json',
        )
        r = joined_client.get('/predicciones/grupos')
        assert r.status_code == 200
        # Check that at least one team name appears in the rendered page
        assert b'M\xc3\xa9xico' in r.data or b'Brasil' in r.data

    def test_unauthenticated_groups_redirects_to_join(self, client):
        r = client.get('/predicciones/grupos')
        assert r.status_code == 302
        assert 'join' in r.headers['Location']

    def test_groups_closed_blocks_save(self, joined_client, app):
        open_phase(app, 'groups_open')
        close_phase(app, 'groups_open')
        r = joined_client.post(
            '/predicciones/grupos',
            data=json.dumps(VALID_GROUPS),
            content_type='application/json',
        )
        assert r.status_code == 403


class TestKnockoutPredictions:
    def _setup_match(self, admin_client):
        admin_client.post(
            '/admin/setup-partido',
            data=json.dumps({'round_id': 'r32', 'match_id': 1,
                             'team1': 'Brasil', 'team2': 'Argentina'}),
            content_type='application/json',
        )

    def test_knockout_closed_by_default(self, joined_client, app, admin_client):
        self._setup_match(admin_client)
        r = joined_client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Brasil'}),
            content_type='application/json',
        )
        assert r.status_code == 403

    def test_knockout_open_allows_pick(self, joined_client, app, admin_client):
        self._setup_match(admin_client)
        open_phase(app, 'r32_open')
        r = joined_client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Brasil'}),
            content_type='application/json',
        )
        assert json.loads(r.data)['ok'] is True

    def test_invalid_team_rejected(self, joined_client, app, admin_client):
        self._setup_match(admin_client)
        open_phase(app, 'r32_open')
        r = joined_client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Inventado FC'}),
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_pick_updates_on_resubmit(self, joined_client, app, admin_client):
        self._setup_match(admin_client)
        open_phase(app, 'r32_open')
        joined_client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Brasil'}),
            content_type='application/json',
        )
        r = joined_client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Argentina'}),
            content_type='application/json',
        )
        assert json.loads(r.data)['ok'] is True

    def test_unauthenticated_pick_returns_401(self, client):
        r = client.post(
            '/predicciones/eliminatorias/pick',
            data=json.dumps({'round_id': 'r32', 'match_id': 1, 'team': 'Brasil'}),
            content_type='application/json',
        )
        assert r.status_code == 401


class TestSpecialPredictions:
    def test_specials_closed_by_default(self, joined_client):
        r = joined_client.post(
            '/predicciones/especiales',
            data=json.dumps({'champion': 'España'}),
            content_type='application/json',
        )
        assert r.status_code == 403

    def test_specials_open_allows_save(self, joined_client, app):
        open_phase(app, 'specials_open')
        r = joined_client.post(
            '/predicciones/especiales',
            data=json.dumps({'champion': 'España', 'top_scorer': 'Mbappé'}),
            content_type='application/json',
        )
        assert json.loads(r.data)['ok'] is True

    def test_special_prediction_persists(self, joined_client, app):
        open_phase(app, 'specials_open')
        joined_client.post(
            '/predicciones/especiales',
            data=json.dumps({'champion': 'España'}),
            content_type='application/json',
        )
        # Re-save with different value (update path)
        r = joined_client.post(
            '/predicciones/especiales',
            data=json.dumps({'champion': 'Argentina'}),
            content_type='application/json',
        )
        assert json.loads(r.data)['ok'] is True

    def test_unknown_category_ignored(self, joined_client, app):
        open_phase(app, 'specials_open')
        r = joined_client.post(
            '/predicciones/especiales',
            data=json.dumps({'fake_category': 'whatever', 'champion': 'Brasil'}),
            content_type='application/json',
        )
        assert json.loads(r.data)['ok'] is True
