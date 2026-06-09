import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

# Force in-memory SQLite for ALL test runs — even inside Docker where DATABASE_URL
# points to PostgreSQL. Using setdefault() was unsafe: if DATABASE_URL was already
# set (Docker env), SQLAlchemy used production PostgreSQL and _db.drop_all() in
# teardown wiped all production data. Force-set to guarantee isolation.
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('ADMIN_PASSWORD', 'testpass')

from main import app as flask_app, socketio, init_db, GROUPS_DEADLINE
from models import db as _db, AppConfig, User, UserScore


@pytest.fixture()
def app():
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,
    })
    with flask_app.app_context():
        _db.create_all()
        init_db()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


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
    """A test client that has already registered a user called 'Tester'."""
    c = app.test_client()
    c.post('/join', data={'name': 'Tester'}, follow_redirects=True)
    return c


def open_phase(app, key):
    with app.app_context():
        AppConfig.set(key, 'true')


def close_phase(app, key):
    with app.app_context():
        AppConfig.set(key, 'false')
