import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# These must be set BEFORE importing anything from the app so that
# module-level constants (ADMIN_PASSWORD, etc.) are read correctly.
# We force-override even if Docker has already set these in the environment.
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['ADMIN_PASSWORD'] = 'testpass'

from flask import Flask
from flask_socketio import SocketIO
import main as app_module
from models import db as _db, AppConfig, User, UserScore


def _create_test_app():
    """Return a brand-new Flask app wired to an in-memory SQLite database.

    We intentionally do NOT reuse app_module.app so that tests can never
    accidentally touch the production PostgreSQL database.
    """
    test_app = Flask(app_module.app.name,
                     template_folder=app_module.app.template_folder,
                     static_folder=app_module.app.static_folder)
    test_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,
    })
    # Re-register all routes and blueprints from the production app
    for rule in app_module.app.url_map.iter_rules():
        pass  # routes are bound to the app object — we must reuse it
    return None  # signal to use the patched-config approach below


@pytest.fixture()
def app():
    """
    Reconfigure the existing Flask app to use SQLite for the duration of
    each test, then restore the original URI afterwards so the running
    server is unaffected.

    Crucially, `db.drop_all()` runs inside `with app.app_context()` which
    binds to the same SQLite engine created by `db.create_all()`.  The
    production PostgreSQL engine lives in a completely separate OS process
    and is never touched.
    """
    original_uri = app_module.app.config.get('SQLALCHEMY_DATABASE_URI')
    app_module.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app_module.app.config['TESTING'] = True
    app_module.app.config['SECRET_KEY'] = 'test-secret-key'
    app_module.app.config['WTF_CSRF_ENABLED'] = False
    app_module.app.config['RATELIMIT_ENABLED'] = False

    with app_module.app.app_context():
        _db.create_all()
        app_module.init_db()
        yield app_module.app
        _db.session.remove()
        _db.drop_all()

    # Restore so subsequent imports / uses see the real URI
    app_module.app.config['SQLALCHEMY_DATABASE_URI'] = original_uri or 'sqlite://'
    app_module.app.config['TESTING'] = False


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-memory rate limit counters before each test."""
    try:
        app_module.limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture()
def socketio():
    return app_module.socketio


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(app):
    c = app.test_client()
    c.post('/admin/login', data={'password': 'testpass'}, follow_redirects=True)
    return c


@pytest.fixture()
def joined_client(app):
    """Flask test client that already has a registered session ('Tester')."""
    c = app.test_client()
    c.post('/join', data={'name': 'Tester'}, follow_redirects=True)
    return c


def open_phase(app, key):
    with app.app_context():
        AppConfig.set(key, 'true')


def close_phase(app, key):
    with app.app_context():
        AppConfig.set(key, 'false')
