import os
import json
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (Flask, render_template, request, session, redirect,
                   url_for, jsonify, flash)
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from models import (db, User, GroupPrediction, KnockoutPrediction,
                    ActualGroupStanding, KnockoutMatch, AppConfig, UserScore,
                    SpecialPrediction, SpecialResult, StreakPick, DiscordLink)
from scoring import recalculate_all_scores, get_leaderboard, award_wildcard, save_snapshot
from wc_data import (DEFAULT_GROUPS, ROUNDS, PHASE_CONFIG, SPECIAL_CATEGORIES,
                     ALL_TEAMS, BRACKET_TREE, SF_LOSER_TO_TP, ROUND_MATCH_COUNTS, flag)
import fetcher

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///porra.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Set SESSION_COOKIE_SECURE = True when running behind HTTPS

db.init_app(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])

app.jinja_env.globals['flag'] = flag

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2026')
BOT_SECRET     = os.environ.get('BOT_SECRET', '')

# Jueves 11 de junio a las 20:00 hora española (CEST = UTC+2) → 18:00 UTC
GROUPS_DEADLINE = datetime(2026, 6, 11, 18, 0, 0, tzinfo=timezone.utc)


def hash_ip(ip: str) -> str:
    """One-way HMAC-SHA256 of an IP address using the app secret key."""
    secret = app.config['SECRET_KEY'].encode()
    return hashlib.sha256(secret + ip.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def get_groups_config():
    raw = AppConfig.get('groups_json')
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return DEFAULT_GROUPS


def get_phase():
    phases = {}
    for key in PHASE_CONFIG:
        phases[key] = AppConfig.get(key, 'false') == 'true'

    # Cierre automático al llegar el deadline del torneo
    if datetime.now(timezone.utc) >= GROUPS_DEADLINE:
        for key in ('groups_open', 'specials_open'):
            if phases.get(key):
                AppConfig.set(key, 'false')
                socketio.emit('phase_updated', phases)
            phases[key] = False

    return phases


def groups_deadline_info():
    now = datetime.now(timezone.utc)
    remaining = GROUPS_DEADLINE - now
    if remaining.total_seconds() <= 0:
        return {'open': False, 'deadline_str': '11 jun · 20:00', 'seconds_left': 0}
    return {
        'open': True,
        'deadline_str': '11 jun · 20:00',
        'seconds_left': int(remaining.total_seconds()),
    }


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _gen_recovery_code():
    """Generate a unique 8-char alphanumeric recovery code (no ambiguous chars)."""
    import random
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no O/0, no I/1
    while True:
        code = ''.join(random.choices(chars, k=8))
        if not User.query.filter_by(recovery_code=code).first():
            return code


def init_db():
    db.create_all()
    # PostgreSQL column migrations
    for sql in [
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_code VARCHAR(10)',
        'ALTER TABLE streak_picks ALTER COLUMN match_date TYPE VARCHAR(50)',
    ]:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

    for key, cfg in PHASE_CONFIG.items():
        if not AppConfig.query.filter_by(key=key).first():
            db.session.add(AppConfig(key=key, value='false'))
    if not AppConfig.query.filter_by(key='groups_json').first():
        db.session.add(AppConfig(key='groups_json',
                                 value=json.dumps(DEFAULT_GROUPS, ensure_ascii=False)))
    for key, default in [('streak_open', 'true'), ('streak_match', ''), ('streak_resolved_dates', '[]')]:
        if not AppConfig.query.filter_by(key=key).first():
            db.session.add(AppConfig(key=key, value=default))
    db.session.commit()
    # Migrate any plain-text IPs still in the DB (contain '.' or ':')
    for user in User.query.all():
        if user.ip and ('.' in user.ip or ':' in user.ip):
            user.ip = hash_ip(user.ip)
        # Generate recovery code for users that don't have one
        if not user.recovery_code:
            user.recovery_code = _gen_recovery_code()
    db.session.commit()


# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------

PORRA_COOKIE = 'porra_uid'
PORRA_COOKIE_MAX_AGE = 365 * 24 * 3600  # 1 year


@app.after_request
def _set_persistent_cookie(response):
    """Stamp the persistent cookie on any authenticated request that lacks it."""
    if request.cookies.get(PORRA_COOKIE):
        return response  # already set
    user_id = session.get('user_id')
    if not user_id:
        return response
    user = User.query.get(user_id)
    if user:
        response.set_cookie(PORRA_COOKIE, user.session_uuid,
                            max_age=PORRA_COOKIE_MAX_AGE,
                            httponly=True, samesite='Lax')
    return response


@app.route('/')
def index():
    user = get_current_user()
    phase = get_phase()
    leaderboard = get_leaderboard()
    groups = get_groups_config()
    from wc_data import TEAM_FLAGS
    flags_json = json.dumps(TEAM_FLAGS, ensure_ascii=False)
    return render_template('index.html', user=user, phase=phase,
                           leaderboard=leaderboard[:10], groups=groups,
                           rounds=ROUNDS, flags_json=flags_json)


@app.route('/api/group-standings')
def api_group_standings():
    standings = {}
    for s in ActualGroupStanding.query.order_by(
            ActualGroupStanding.group_name, ActualGroupStanding.position).all():
        standings.setdefault(s.group_name, []).append(
            {'pos': s.position, 'team': s.team_name})
    return jsonify(standings)


@app.route('/api/upcoming-matches')
def api_upcoming_matches():
    matches = fetcher.fetch_upcoming_matches()
    return jsonify({'matches': matches or []})


def _restore_from_cookie():
    """Return User if the persistent cookie matches a known account, else None."""
    uid = request.cookies.get(PORRA_COOKIE)
    if uid:
        return User.query.filter_by(session_uuid=uid).first()
    return None


@app.route('/recuperar', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def recover():
    if get_current_user():
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        user = User.query.filter_by(recovery_code=code).first()
        if not user:
            error = 'Código incorrecto. Comprueba que no haya espacios ni errores.'
        else:
            session['user_id'] = user.id
            resp = redirect(url_for('index'))
            resp.set_cookie(PORRA_COOKIE, user.session_uuid,
                            max_age=PORRA_COOKIE_MAX_AGE,
                            httponly=True, samesite='Lax')
            flash(f'¡Bienvenido de vuelta, {user.name}!', 'success')
            return resp
    return render_template('recover.html', error=error)


@app.route('/join', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def join():
    if get_current_user():
        return redirect(url_for('index'))

    # Persistent cookie check — works even after logout
    existing = _restore_from_cookie()
    if existing:
        session['user_id'] = existing.id
        flash(f'Ya tienes cuenta como {existing.name}. Te hemos recuperado la sesión.', 'info')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name or len(name) > 30:
            flash('El nombre debe tener entre 1 y 30 caracteres.', 'danger')
            return render_template('join.html')
        if User.query.filter(db.func.lower(User.name) == name.lower()).first():
            flash(f'El nombre "{name}" ya está en uso. Elige otro.', 'danger')
            return render_template('join.html')
        raw_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        ip = hash_ip(raw_ip.split(',')[0].strip())
        uid = str(uuid.uuid4())
        user = User(session_uuid=uid, name=name, ip=ip,
                    recovery_code=_gen_recovery_code())
        db.session.add(user)
        db.session.flush()
        db.session.add(UserScore(user_id=user.id, group_points=0,
                                 knockout_points=0, total_points=0))
        db.session.commit()
        session['user_id'] = user.id
        flash(f'¡Bienvenido, {name}! Ya puedes hacer tus predicciones.', 'success')
        resp = redirect(url_for('index'))
        resp.set_cookie(PORRA_COOKIE, uid, max_age=PORRA_COOKIE_MAX_AGE,
                        httponly=True, samesite='Lax')
        return resp
    return render_template('join.html')


@app.route('/salir')
def logout():
    session.clear()
    # Keep the persistent cookie so re-joining restores the same account
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Group predictions
# ---------------------------------------------------------------------------

@app.route('/predicciones/grupos', methods=['GET', 'POST'])
@csrf.exempt
def predict_groups():
    user = get_current_user()
    if not user:
        return redirect(url_for('join'))

    phase = get_phase()
    groups = get_groups_config()

    existing = {}
    for pred in GroupPrediction.query.filter_by(user_id=user.id).all():
        existing.setdefault(pred.group_name, {})[pred.position] = pred.team_name

    if request.method == 'POST':
        if not phase['groups_open']:
            return jsonify({'ok': False, 'msg': 'Las predicciones de grupos están cerradas.'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'msg': 'Datos inválidos.'}), 400

        GroupPrediction.query.filter_by(user_id=user.id).delete()
        for group_name, teams in data.items():
            if group_name not in groups:
                continue
            for pos, team in enumerate(teams, 1):
                db.session.add(GroupPrediction(
                    user_id=user.id,
                    group_name=group_name,
                    team_name=team,
                    position=pos,
                ))
        db.session.commit()
        return jsonify({'ok': True, 'msg': '¡Predicciones guardadas!'})

    return render_template('groups.html', user=user, phase=phase,
                           groups=groups, existing=existing,
                           deadline=groups_deadline_info())


# ---------------------------------------------------------------------------
# Knockout bracket
# ---------------------------------------------------------------------------

@app.route('/predicciones/eliminatorias')
def predict_bracket():
    user = get_current_user()
    if not user:
        return redirect(url_for('join'))

    phase = get_phase()
    bracket_any_open = phase.get('bracket_open', False) or any(
        phase.get(f'{r["id"]}_open', False) for r in ROUNDS
    )

    matches_by_round = {}
    for r in ROUNDS:
        matches_by_round[r['id']] = {
            m.match_id: m
            for m in KnockoutMatch.query.filter_by(round_id=r['id']).all()
        }

    user_picks = {}
    for pred in KnockoutPrediction.query.filter_by(user_id=user.id).all():
        user_picks[(pred.round_id, pred.match_id)] = pred.predicted_winner

    # Build compact JSON structures for JS cascade
    actual_teams = {}
    for r in ROUNDS:
        actual_teams[r['id']] = {}
        for mid, m in matches_by_round[r['id']].items():
            actual_teams[r['id']][mid] = {
                't1': m.team1 or '', 't2': m.team2 or '', 'w': m.winner or ''
            }

    picks_by_round = {}
    for (rid, mid), team in user_picks.items():
        picks_by_round.setdefault(rid, {})[mid] = team

    return render_template('bracket.html', user=user, phase=phase,
                           bracket_any_open=bracket_any_open,
                           rounds=ROUNDS, matches_by_round=matches_by_round,
                           round_match_counts=ROUND_MATCH_COUNTS,
                           user_picks=user_picks,
                           actual_teams_json=json.dumps(actual_teams),
                           picks_json=json.dumps(picks_by_round),
                           flags_json=json.dumps(
                               {t: flag(t) for teams in get_groups_config().values() for t in teams}
                           ))


@app.route('/predicciones/eliminatorias/pick', methods=['POST'])
@csrf.exempt
def pick_knockout():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False, 'msg': 'No identificado.'}), 401

    data = request.get_json()
    round_id = data.get('round_id')
    match_id = data.get('match_id')
    team = data.get('team')
    use_wildcard = data.get('wildcard', False)

    if not round_id or not match_id or not team:
        return jsonify({'ok': False, 'msg': 'Datos incompletos.'}), 400

    phase = get_phase()
    phase_key = f'{round_id}_open'
    is_open = phase.get(phase_key, False) or phase.get('bracket_open', False)

    if not is_open:
        if use_wildcard and user.has_wildcard and not user.wildcard_used:
            pass  # wildcard allows picking a closed round
        else:
            return jsonify({'ok': False, 'msg': 'Esta ronda está cerrada.'}), 403

    # Validate team is a known participant
    groups = get_groups_config()
    all_teams_set = {t for grp in groups.values() for t in grp}
    if team not in all_teams_set:
        return jsonify({'ok': False, 'msg': 'Equipo desconocido.'}), 400

    match = KnockoutMatch.query.filter_by(round_id=round_id, match_id=match_id).first()

    # If match has actual confirmed teams, only allow picking one of them
    if match and match.team1 and match.team2:
        if team not in [match.team1, match.team2]:
            return jsonify({'ok': False, 'msg': 'Ese equipo no juega este partido.'}), 400

    # Create a placeholder match record if one doesn't exist yet
    if not match:
        match = KnockoutMatch(round_id=round_id, match_id=match_id, team1='', team2='')
        db.session.add(match)
        db.session.flush()

    pred = KnockoutPrediction.query.filter_by(
        user_id=user.id, round_id=round_id, match_id=match_id).first()

    if pred:
        if not is_open:
            if use_wildcard and user.has_wildcard and not user.wildcard_used:
                pred.predicted_winner = team
                pred.is_wildcard = True
                user.wildcard_used = True
                db.session.commit()
                return jsonify({'ok': True, 'msg': '¡Comodín usado!'})
            return jsonify({'ok': False, 'msg': 'Ronda cerrada.'}), 403
        pred.predicted_winner = team
    else:
        db.session.add(KnockoutPrediction(
            user_id=user.id, round_id=round_id,
            match_id=match_id, predicted_winner=team))

    if use_wildcard and user.has_wildcard and not user.wildcard_used:
        user.wildcard_used = True

    db.session.commit()
    return jsonify({'ok': True, 'msg': '¡Predicción guardada!'})


# ---------------------------------------------------------------------------
# Special predictions
# ---------------------------------------------------------------------------

@app.route('/predicciones/especiales', methods=['GET', 'POST'])
@csrf.exempt
def predict_specials():
    user = get_current_user()
    if not user:
        return redirect(url_for('join'))

    phase = get_phase()
    existing = {p.category: p.predicted_value
                for p in SpecialPrediction.query.filter_by(user_id=user.id).all()}
    results = {r.category: r.actual_value for r in SpecialResult.query.all()}

    if request.method == 'POST':
        if not phase['specials_open']:
            return jsonify({'ok': False, 'msg': 'Las predicciones especiales están cerradas.'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'msg': 'Datos inválidos.'}), 400

        valid_ids = {c['id'] for c in SPECIAL_CATEGORIES}
        for cat_id, value in data.items():
            if cat_id not in valid_ids:
                continue
            value = value.strip()
            if not value:
                continue
            pred = SpecialPrediction.query.filter_by(user_id=user.id, category=cat_id).first()
            if pred:
                pred.predicted_value = value
            else:
                db.session.add(SpecialPrediction(user_id=user.id, category=cat_id, predicted_value=value))
        db.session.commit()
        return jsonify({'ok': True, 'msg': '¡Predicciones especiales guardadas!'})

    return render_template('specials.html', user=user, phase=phase,
                           categories=SPECIAL_CATEGORIES, all_teams=ALL_TEAMS,
                           existing=existing, results=results,
                           deadline=groups_deadline_info())


@app.route('/admin/delete-user', methods=['POST'])
@csrf.exempt
@admin_required
def admin_delete_user():
    data = request.get_json()
    user_id = data.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'ok': False, 'msg': 'Usuario no encontrado.'}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({'ok': True, 'msg': f'Usuario "{user.name}" eliminado.'})


@app.route('/admin/link-discord', methods=['POST'])
@csrf.exempt
@admin_required
def admin_link_discord():
    data = request.get_json()
    user_id    = data.get('user_id')
    discord_id = (data.get('discord_id') or '').strip()
    if not user_id:
        return jsonify({'ok': False, 'msg': 'user_id requerido.'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'ok': False, 'msg': 'Usuario no encontrado.'}), 404
    if not discord_id:
        # Unlink
        DiscordLink.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({'ok': True, 'msg': 'Vinculación eliminada.'})
    # Check not taken by another user
    existing = DiscordLink.query.filter_by(discord_id=discord_id).first()
    if existing and existing.user_id != user_id:
        return jsonify({'ok': False, 'msg': 'Ese Discord ID ya está vinculado a otro usuario.'}), 400
    link = DiscordLink.query.filter_by(user_id=user_id).first()
    if link:
        link.discord_id = discord_id
        link.discord_name = data.get('discord_name', link.discord_name)
    else:
        db.session.add(DiscordLink(user_id=user_id, discord_id=discord_id,
                                   discord_name=data.get('discord_name', '')))
    db.session.commit()
    return jsonify({'ok': True, 'msg': f'Vinculado Discord {discord_id} → {user.name}.'})


@app.route('/admin/rename-user', methods=['POST'])
@csrf.exempt
@admin_required
def admin_rename_user():
    data = request.get_json()
    user_id = data.get('user_id')
    new_name = (data.get('name') or '').strip()
    if not user_id or not new_name or len(new_name) > 30:
        return jsonify({'ok': False, 'msg': 'Nombre inválido (1-30 caracteres).'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'ok': False, 'msg': 'Usuario no encontrado.'}), 404
    user.name = new_name
    db.session.commit()
    return jsonify({'ok': True, 'msg': f'Nombre cambiado a "{new_name}".'})


@app.route('/admin/resultado-especial', methods=['POST'])
@csrf.exempt
@admin_required
def admin_special_result():
    data = request.get_json()
    category = data.get('category', '').strip()
    value = data.get('value', '').strip()
    valid_ids = {c['id'] for c in SPECIAL_CATEGORIES}
    if not category or category not in valid_ids or not value:
        return jsonify({'ok': False, 'msg': 'Datos inválidos.'}), 400
    row = SpecialResult.query.filter_by(category=category).first()
    if row:
        row.actual_value = value
    else:
        db.session.add(SpecialResult(category=category, actual_value=value))
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@app.route('/clasificacion')
def leaderboard():
    user = get_current_user()
    board = get_leaderboard()
    phase = get_phase()
    return render_template('leaderboard.html', user=user,
                           leaderboard=board, phase=phase)


@app.route('/clasificacion-racha')
def streak_leaderboard():
    user = get_current_user()
    stats_map = _streak_stats_for_users()
    rankings = [
        {'user_id': uid, 'name': d['name'], 'current': d['current'],
         'max': d['max'], 'points': d['points']}
        for uid, d in stats_map.items()
        if d['points'] > 0 or d['current'] > 0 or d['max'] > 0
    ]
    rankings.sort(key=lambda x: (-x['points'], -x['current'], -x['max']))
    raw = AppConfig.get('streak_match', '')
    match_data = None
    if raw:
        try:
            match_data = json.loads(raw)
        except Exception:
            pass
    votes = {'home': 0, 'draw': 0, 'away': 0}
    if match_data:
        for p in StreakPick.query.filter_by(match_date=match_data['date']).all():
            if p.pick in votes:
                votes[p.pick] += 1
    total_votes = sum(votes.values())
    votes_pct = {k: round(v * 100 / total_votes) if total_votes else 0 for k, v in votes.items()}
    return render_template('streak_leaderboard.html', user=user,
                           rankings=rankings, match=match_data,
                           votes=votes, votes_pct=votes_pct, total_votes=total_votes)


@app.route('/estadisticas')
def stats():
    user = get_current_user()
    total_users = User.query.count()

    # --- Special predictions consensus ---
    special_stats = []
    for cat in SPECIAL_CATEGORIES:
        rows = (
            db.session.query(SpecialPrediction.predicted_value,
                             db.func.count().label('cnt'))
            .filter_by(category=cat['id'])
            .group_by(SpecialPrediction.predicted_value)
            .order_by(db.text('cnt DESC'))
            .limit(5)
            .all()
        )
        if rows:
            special_stats.append({
                'category': cat,
                'picks': [{'value': r.predicted_value, 'count': r.cnt,
                           'pct': round(r.cnt / total_users * 100) if total_users else 0}
                          for r in rows],
            })

    # --- Group stage consensus: most popular pick per position ---
    groups = get_groups_config()
    group_stats = {}
    for letter in groups:
        pos_data = {}
        for pos in range(1, 5):
            rows = (
                db.session.query(GroupPrediction.team_name,
                                 db.func.count().label('cnt'))
                .filter_by(group_name=letter, position=pos)
                .group_by(GroupPrediction.team_name)
                .order_by(db.text('cnt DESC'))
                .limit(4)
                .all()
            )
            if rows:
                pos_data[pos] = [{'team': r.team_name, 'count': r.cnt,
                                   'pct': round(r.cnt / total_users * 100) if total_users else 0}
                                  for r in rows]
        if pos_data:
            group_stats[letter] = pos_data

    # --- Knockout consensus ---
    knockout_stats = []
    for r in ROUNDS:
        matches = KnockoutMatch.query.filter_by(round_id=r['id']).order_by(KnockoutMatch.match_id).all()
        match_rows = []
        for m in matches:
            picks = (
                db.session.query(KnockoutPrediction.predicted_winner,
                                 db.func.count().label('cnt'))
                .filter_by(round_id=r['id'], match_id=m.match_id)
                .group_by(KnockoutPrediction.predicted_winner)
                .order_by(db.text('cnt DESC'))
                .all()
            )
            total_picks = sum(p.cnt for p in picks)
            if picks:
                match_rows.append({
                    'match': m,
                    'picks': [{'team': p.predicted_winner, 'count': p.cnt,
                                'pct': round(p.cnt / total_picks * 100) if total_picks else 0}
                               for p in picks],
                    'total': total_picks,
                })
        if match_rows:
            knockout_stats.append({'round': r, 'matches': match_rows})

    return render_template('estadisticas.html', user=user,
                           total_users=total_users,
                           special_stats=special_stats,
                           group_stats=group_stats,
                           groups=groups,
                           knockout_stats=knockout_stats,
                           rounds=ROUNDS)


# ---------------------------------------------------------------------------
# Predictions profile (own + public)
# ---------------------------------------------------------------------------

def _build_predictions_context(profile_user, groups, phase):
    """Return group_rows, matches_by_round, ko_any_pick, and display_teams for any user."""
    predicted_groups = {}
    for pred in GroupPrediction.query.filter_by(user_id=profile_user.id).all():
        predicted_groups.setdefault(pred.group_name, {})[pred.position] = pred.team_name

    actual_pos = {}
    for standing in ActualGroupStanding.query.all():
        actual_pos.setdefault(standing.group_name, {})[standing.team_name] = standing.position

    group_rows = {}
    for group_letter in groups:
        rows = []
        preds = predicted_groups.get(group_letter, {})
        actuals = actual_pos.get(group_letter, {})
        for pos in range(1, 5):
            team = preds.get(pos)
            if team is None:
                continue
            a_pos = actuals.get(team)
            correct = (a_pos == pos) if a_pos is not None else None
            rows.append({'pos': pos, 'team': team, 'actual_pos': a_pos, 'correct': correct})
        if rows:
            group_rows[group_letter] = rows

    ko_picks = {
        (p.round_id, p.match_id): p.predicted_winner
        for p in KnockoutPrediction.query.filter_by(user_id=profile_user.id).all()
    }
    ko_any_pick = bool(ko_picks)

    matches_by_round = {}  # {round_id: {match_id: {match, pick, correct}}}
    for r in ROUNDS:
        round_matches = KnockoutMatch.query.filter_by(
            round_id=r['id']).order_by(KnockoutMatch.match_id).all()
        round_dict = {}
        for m in round_matches:
            pick = ko_picks.get((r['id'], m.match_id))
            correct = None
            if pick and m.winner:
                correct = (pick == m.winner)
            round_dict[m.match_id] = {'match': m, 'pick': pick, 'correct': correct}
        if round_dict:
            matches_by_round[r['id']] = round_dict

    # Cascade picks into later empty slots for display purposes
    display_teams = {}  # {round_id: {match_id: {'t1': str, 't2': str}}}
    for r in ROUNDS:
        r_id = r['id']
        count = ROUND_MATCH_COUNTS.get(r_id, 0)
        display_teams[r_id] = {}
        for mid in range(1, count + 1):
            row = matches_by_round.get(r_id, {}).get(mid)
            m = row['match'] if row else None
            display_teams[r_id][mid] = {'t1': (m.team1 or '') if m else '',
                                         't2': (m.team2 or '') if m else ''}

    for round_id in ['r32', 'r16', 'qf', 'sf']:
        for match_id, (next_round, next_match, slot) in BRACKET_TREE[round_id].items():
            pick = ko_picks.get((round_id, match_id))
            if not pick:
                continue
            slot_data = display_teams[next_round][next_match]
            if slot == 0 and not slot_data['t1']:
                slot_data['t1'] = pick
            elif slot == 1 and not slot_data['t2']:
                slot_data['t2'] = pick

    return group_rows, matches_by_round, ko_any_pick, display_teams


@app.route('/mis-predicciones')
def my_predictions():
    user = get_current_user()
    if not user:
        return redirect(url_for('join'))
    return redirect(url_for('user_profile', user_id=user.id))


@app.route('/perfil/<int:user_id>')
def user_profile(user_id):
    current_user = get_current_user()
    profile_user = User.query.get(user_id)
    if not profile_user:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('leaderboard'))

    groups = get_groups_config()
    phase = get_phase()
    group_rows, matches_by_round, ko_any_pick, display_teams = _build_predictions_context(
        profile_user, groups, phase)
    is_own = current_user and current_user.id == profile_user.id

    return render_template('mis_predicciones.html',
                           user=current_user, profile_user=profile_user,
                           is_own=is_own, phase=phase, groups=groups,
                           group_rows=group_rows, rounds=ROUNDS,
                           matches_by_round=matches_by_round,
                           ko_any_pick=ko_any_pick,
                           display_teams=display_teams,
                           round_counts=ROUND_MATCH_COUNTS)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('10 per 10 minutes', methods=['POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
        flash('Contraseña incorrecta.', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_panel():
    phase = get_phase()
    groups = get_groups_config()
    users = (db.session.query(User, UserScore)
             .outerjoin(UserScore, User.id == UserScore.user_id)
             .order_by(db.func.coalesce(UserScore.total_points, 0).desc())
             .all())
    matches_by_round = {}
    for r in ROUNDS:
        matches_by_round[r['id']] = KnockoutMatch.query.filter_by(
            round_id=r['id']).order_by(KnockoutMatch.match_id).all()
    actual_standings = {}
    for s in ActualGroupStanding.query.all():
        actual_standings.setdefault(s.group_name, {})[s.position] = s.team_name

    special_results = {r.category: r.actual_value for r in SpecialResult.query.all()}
    discord_links = {dl.user_id: dl for dl in DiscordLink.query.all()}

    return render_template('admin.html', phase=phase, groups=groups,
                           users=users, rounds=ROUNDS,
                           matches_by_round=matches_by_round,
                           actual_standings=actual_standings,
                           phase_config=PHASE_CONFIG,
                           groups_json=json.dumps(groups, ensure_ascii=False, indent=2),
                           special_categories=SPECIAL_CATEGORIES,
                           special_results=special_results,
                           all_teams=ALL_TEAMS,
                           discord_links=discord_links,
                           last_api_sync=AppConfig.get('last_api_sync'))


@app.route('/admin/phase', methods=['POST'])
@admin_required
def admin_toggle_phase():
    key = request.form.get('key')
    if key not in PHASE_CONFIG:
        flash('Fase inválida.', 'danger')
        return redirect(url_for('admin_panel'))
    current = AppConfig.get(key, 'false')
    AppConfig.set(key, 'false' if current == 'true' else 'true')
    phase = get_phase()
    socketio.emit('phase_updated', phase)
    flash(f'Fase actualizada.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/grupos-config', methods=['POST'])
@admin_required
def admin_update_groups():
    raw = request.form.get('groups_json', '')
    try:
        parsed = json.loads(raw)
        AppConfig.set('groups_json', json.dumps(parsed, ensure_ascii=False))
        flash('Grupos actualizados correctamente.', 'success')
    except Exception as e:
        flash(f'JSON inválido: {e}', 'danger')
    return redirect(url_for('admin_panel'))


@app.route('/admin/resultados-grupos', methods=['POST'])
@csrf.exempt
@admin_required
def admin_group_results():
    data = request.get_json()
    group_name = data.get('group')
    teams = data.get('teams', [])
    if not group_name or len(teams) != 4:
        return jsonify({'ok': False, 'msg': 'Datos inválidos.'}), 400

    ActualGroupStanding.query.filter_by(group_name=group_name).delete()
    for pos, team in enumerate(teams, 1):
        db.session.add(ActualGroupStanding(
            group_name=group_name, team_name=team, position=pos))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/setup-partido', methods=['POST'])
@csrf.exempt
@admin_required
def admin_setup_match():
    data = request.get_json()
    round_id = data.get('round_id')
    match_id = data.get('match_id')
    team1 = data.get('team1', '').strip()
    team2 = data.get('team2', '').strip()

    if not all([round_id, match_id, team1, team2]):
        return jsonify({'ok': False, 'msg': 'Faltan datos.'}), 400

    match = KnockoutMatch.query.filter_by(
        round_id=round_id, match_id=match_id).first()
    if match:
        match.team1 = team1
        match.team2 = team2
        match.winner = None
    else:
        db.session.add(KnockoutMatch(round_id=round_id, match_id=match_id,
                                     team1=team1, team2=team2))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/resultado-partido', methods=['POST'])
@csrf.exempt
@admin_required
def admin_match_result():
    data = request.get_json()
    round_id = data.get('round_id')
    match_id = data.get('match_id')
    winner = data.get('winner', '').strip()

    match = KnockoutMatch.query.filter_by(
        round_id=round_id, match_id=match_id).first()
    if not match:
        return jsonify({'ok': False, 'msg': 'Partido no encontrado.'}), 404
    if winner not in [match.team1, match.team2]:
        return jsonify({'ok': False, 'msg': 'Ganador inválido.'}), 400

    match.winner = winner
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/recalcular', methods=['POST'])
@admin_required
def admin_recalculate():
    label = request.form.get('label', '').strip() or _auto_snapshot_label()
    recalculate_all_scores()
    save_snapshot(label)
    board = get_leaderboard()
    socketio.emit('scores_updated', {'leaderboard': board})
    flash('¡Puntuaciones recalculadas y enviadas en tiempo real!', 'success')
    return redirect(url_for('admin_panel'))


def _auto_snapshot_label():
    """Derive a snapshot label from which phases are currently open."""
    phase = get_phase()
    for r in ROUNDS:
        if phase.get(f'{r["id"]}_open'):
            return r['name']
    return 'Grupos'


@app.route('/admin/comodin', methods=['POST'])
@admin_required
def admin_award_wildcard():
    winner_name = award_wildcard()
    if winner_name:
        flash(f'Comodín otorgado a {winner_name}.', 'success')
        socketio.emit('wildcard_awarded', {'name': winner_name})
    else:
        flash('No hay usuarios para otorgar el comodín.', 'warning')
    return redirect(url_for('admin_panel'))


@app.route('/admin/comodin/quitar', methods=['POST'])
@csrf.exempt
@admin_required
def admin_revoke_wildcard():
    data = request.get_json()
    user = User.query.get(data.get('user_id'))
    if not user:
        return jsonify({'ok': False, 'msg': 'Usuario no encontrado.'}), 404
    user.has_wildcard = False
    user.wildcard_used = False
    db.session.commit()
    return jsonify({'ok': True, 'msg': f'Comodín retirado a {user.name}.'})


# ---------------------------------------------------------------------------
# Streak helpers
# ---------------------------------------------------------------------------

def _get_resolved_dates():
    """Returns sorted list of all match dates that have had a result set."""
    raw = AppConfig.get('streak_resolved_dates', '[]')
    try:
        return sorted(json.loads(raw))
    except Exception:
        return []


def _calc_streak_stats(date_results):
    """
    Given a list of (date, correct_or_none) sorted by date, compute stats.
    correct_or_none: True = acertó, False = falló, None = no votó (pierde racha).
    Points: nth correct in a row earns n*10. Missing/wrong resets streak to 0.
    Returns (current_streak, max_streak, total_points).
    """
    running = max_s = points = 0
    for _, outcome in date_results:
        if outcome is True:
            running += 1
            points += running * 10
            max_s = max(max_s, running)
        else:
            running = 0
    return running, max_s, points


def _streak_stats_for_users():
    """
    Returns {user_id: {'name', 'current', 'max', 'points'}} for all users
    that have participated or missed at least one resolved match.
    Not voting on a resolved match counts as streak reset.
    """
    resolved_dates = _get_resolved_dates()
    if not resolved_dates:
        return {}

    picks = (db.session.query(StreakPick, User.name)
             .join(User, StreakPick.user_id == User.id)
             .filter(StreakPick.correct.isnot(None))
             .order_by(StreakPick.user_id, StreakPick.match_date.asc())
             .all())

    by_user: dict = {}
    for pick, name in picks:
        uid = pick.user_id
        if uid not in by_user:
            by_user[uid] = {'name': name, 'pick_map': {}}
        by_user[uid]['pick_map'][pick.match_date] = pick.correct

    # Also include users who have any pick (even pending) so their name is known
    all_picks_names = (db.session.query(StreakPick.user_id, User.name)
                       .join(User, StreakPick.user_id == User.id)
                       .distinct()
                       .all())
    for uid, name in all_picks_names:
        if uid not in by_user:
            by_user[uid] = {'name': name, 'pick_map': {}}

    result = {}
    for user_id, data in by_user.items():
        date_results = [(d, data['pick_map'].get(d, None)) for d in resolved_dates]
        current, max_s, points = _calc_streak_stats(date_results)
        result[user_id] = {
            'name': data['name'],
            'current': current,
            'max': max_s,
            'points': points,
        }
    return result


def get_streak_stats(user_id):
    """Returns (current_streak, max_streak, points) for one user."""
    resolved_dates = _get_resolved_dates()
    if not resolved_dates:
        return 0, 0, 0
    picks = {p.match_date: p.correct
             for p in StreakPick.query
             .filter_by(user_id=user_id)
             .filter(StreakPick.correct.isnot(None))
             .all()}
    date_results = [(d, picks.get(d, None)) for d in resolved_dates]
    return _calc_streak_stats(date_results)


def get_streak_rankings():
    """Returns list of dicts sorted by points desc, then current streak."""
    stats = _streak_stats_for_users()
    rankings = [
        {'user_id': uid, 'name': d['name'], 'current': d['current'],
         'max': d['max'], 'points': d['points']}
        for uid, d in stats.items()
        if d['points'] > 0 or d['current'] > 0 or d['max'] > 0
    ]
    rankings.sort(key=lambda x: (-x['points'], -x['current'], -x['max']))
    return rankings[:10]


# ---------------------------------------------------------------------------
# Streak routes
# ---------------------------------------------------------------------------

@app.route('/api/streak')
def api_streak():
    raw = AppConfig.get('streak_match', '')
    match_data = None
    if raw:
        try:
            match_data = json.loads(raw)
        except Exception:
            pass

    user = get_current_user()
    my_pick = None
    my_streak = {'current': 0, 'max': 0}

    votes = {'home': 0, 'draw': 0, 'away': 0}
    if match_data:
        for p in StreakPick.query.filter_by(match_date=match_data['date']).all():
            if p.pick in votes:
                votes[p.pick] += 1

    if user and match_data:
        sp = StreakPick.query.filter_by(
            user_id=user.id, match_date=match_data['date']).first()
        if sp:
            my_pick = sp.pick
        cur, mx, pts = get_streak_stats(user.id)
        my_streak = {'current': cur, 'max': mx, 'points': pts}

    total_votes = sum(votes.values())
    votes_pct = {k: round(v * 100 / total_votes) if total_votes else 0 for k, v in votes.items()}

    return jsonify({
        'match': match_data,
        'my_pick': my_pick,
        'my_streak': my_streak,
        'locked': bool(match_data and match_data.get('result')),
        'rankings': get_streak_rankings(),
        'votes': votes,
        'votes_pct': votes_pct,
        'votes_total': total_votes,
        'force_notify': AppConfig.get('streak_force_notify', '0') == '1',
        'last_notified_key': AppConfig.get('streak_last_notified', ''),
        'send_recovery_dms': AppConfig.get('send_recovery_dms', '0') == '1',
    })


@app.route('/api/streak/votes')
def api_streak_votes():
    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'ok': False, 'msg': 'No hay partido configurado.'}), 404
    try:
        match_data = json.loads(raw)
    except Exception:
        return jsonify({'ok': False}), 500

    picks = StreakPick.query.filter_by(match_date=match_data['date']).all()
    counts = {'home': 0, 'draw': 0, 'away': 0}
    for p in picks:
        if p.pick in counts:
            counts[p.pick] += 1
    total = sum(counts.values())
    pct = {k: round(v * 100 / total) if total else 0 for k, v in counts.items()}
    return jsonify({
        'match': match_data,
        'total': total,
        'counts': counts,
        'pct': pct,
    })


@app.route('/api/streak/rankings')
def api_streak_rankings():
    stats = _streak_stats_for_users()
    rankings = [
        {'user_id': uid, 'name': d['name'], 'current': d['current'], 'max': d['max']}
        for uid, d in stats.items()
        if d['current'] > 0 or d['max'] > 0
    ]
    rankings.sort(key=lambda x: (-x['current'], -x['max']))
    return jsonify({'rankings': rankings})


@app.route('/api/streak/pick', methods=['POST'])
@csrf.exempt
def api_streak_pick():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False, 'msg': 'No identificado.'}), 401

    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'ok': False, 'msg': 'No hay partido configurado hoy.'}), 400
    try:
        match_data = json.loads(raw)
    except Exception:
        return jsonify({'ok': False, 'msg': 'Error de configuración.'}), 500

    if match_data.get('result'):
        return jsonify({'ok': False, 'msg': 'El resultado ya ha sido registrado.'}), 403

    pick = (request.get_json() or {}).get('pick', '')
    if pick not in ('home', 'draw', 'away'):
        return jsonify({'ok': False, 'msg': 'Opción inválida.'}), 400

    existing = StreakPick.query.filter_by(
        user_id=user.id, match_date=match_data['date']).first()
    if existing:
        existing.pick = pick
    else:
        db.session.add(StreakPick(
            user_id=user.id, match_date=match_data['date'], pick=pick))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/streak/next-from-api', methods=['POST'])
@csrf.exempt
@admin_required
def admin_streak_next_from_api():
    matches = fetcher.fetch_upcoming_matches(days_ahead=7)
    if not matches:
        return jsonify({'ok': False, 'msg': 'No se pudo contactar con la API.'}), 503
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    candidates = [
        m for m in matches
        if m['stage'] == 'GROUP_STAGE'
        and m['status'] in ('TIMED', 'SCHEDULED', 'IN_PLAY', 'PAUSED')
        and m['date'][:10] >= today
    ]
    candidates.sort(key=lambda m: m['date'])
    if not candidates:
        return jsonify({'ok': False, 'msg': 'No hay próximos partidos de grupos en la API.'}), 404
    nxt = candidates[0]
    match_data = {
        'date': nxt['date'][:10],
        'home': nxt['home'],
        'away': nxt['away'],
        'result': None,
    }
    AppConfig.set('streak_match', json.dumps(match_data, ensure_ascii=False))
    return jsonify({'ok': True, 'match': match_data})


@app.route('/admin/streak/set-match', methods=['POST'])
@csrf.exempt
@admin_required
def admin_streak_set_match():
    data = request.get_json() or {}
    home = data.get('home', '').strip()
    away = data.get('away', '').strip()
    date = data.get('date', '').strip()
    if not home or not away or not date:
        return jsonify({'ok': False, 'msg': 'Faltan datos.'}), 400
    AppConfig.set('streak_match', json.dumps(
        {'date': date, 'home': home, 'away': away, 'result': None},
        ensure_ascii=False))
    return jsonify({'ok': True})


@app.route('/admin/streak/notify-now', methods=['POST'])
@csrf.exempt
@admin_required
def admin_streak_notify_now():
    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'ok': False, 'msg': 'No hay partido configurado.'}), 400
    AppConfig.set('streak_force_notify', '1')
    return jsonify({'ok': True})


@app.route('/api/streak/clear-notify', methods=['POST'])
@csrf.exempt
def api_streak_clear_notify():
    if not _bot_auth():
        return jsonify({'ok': False}), 403
    data = request.get_json() or {}
    AppConfig.set('streak_force_notify', '0')
    if data.get('match_key'):
        AppConfig.set('streak_last_notified', data['match_key'])
    return jsonify({'ok': True})


@app.route('/api/streak/mark-notified', methods=['POST'])
@csrf.exempt
def api_streak_mark_notified():
    if not _bot_auth():
        return jsonify({'ok': False}), 403
    data = request.get_json() or {}
    match_key = data.get('match_key', '')
    if match_key:
        AppConfig.set('streak_last_notified', match_key)
    return jsonify({'ok': True})


@app.route('/admin/send-recovery-dms', methods=['POST'])
@csrf.exempt
@admin_required
def admin_send_recovery_dms():
    AppConfig.set('send_recovery_dms', '1')
    return jsonify({'ok': True})


@app.route('/api/discord/recovery-codes')
@csrf.exempt
def api_discord_recovery_codes():
    if not _bot_auth():
        return jsonify({'ok': False}), 403
    links = DiscordLink.query.all()
    result = []
    for link in links:
        user = User.query.get(link.user_id)
        if user and user.recovery_code:
            result.append({'discord_id': link.discord_id, 'name': user.name, 'recovery_code': user.recovery_code})
    AppConfig.set('send_recovery_dms', '0')
    return jsonify({'ok': True, 'users': result})


@app.route('/admin/streak/set-result', methods=['POST'])
@csrf.exempt
@admin_required
def admin_streak_set_result():
    data = request.get_json() or {}
    result = data.get('result', '')
    if result not in ('home', 'draw', 'away'):
        return jsonify({'ok': False, 'msg': 'Resultado inválido.'}), 400

    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'ok': False, 'msg': 'No hay partido configurado.'}), 400
    try:
        match_data = json.loads(raw)
    except Exception:
        return jsonify({'ok': False, 'msg': 'Error de configuración.'}), 500

    match_data['result'] = result
    AppConfig.set('streak_match', json.dumps(match_data, ensure_ascii=False))

    # Track this date as resolved
    resolved_raw = AppConfig.get('streak_resolved_dates', '[]')
    try:
        resolved_dates = json.loads(resolved_raw)
    except Exception:
        resolved_dates = []
    if match_data['date'] not in resolved_dates:
        resolved_dates.append(match_data['date'])
        resolved_dates.sort()
        AppConfig.set('streak_resolved_dates', json.dumps(resolved_dates))

    picks = StreakPick.query.filter_by(match_date=match_data['date']).all()
    for p in picks:
        p.correct = (p.pick == result)
    db.session.commit()

    socketio.emit('streak_updated', {'rankings': get_streak_rankings()})
    return jsonify({'ok': True, 'updated': len(picks)})


# ---------------------------------------------------------------------------
# API – Discord bot
# ---------------------------------------------------------------------------

def _bot_auth():
    """Return True if the request carries the correct bot secret."""
    return BOT_SECRET and request.headers.get('X-Bot-Secret') == BOT_SECRET


@app.route('/api/discord/vincular', methods=['POST'])
@csrf.exempt
def api_discord_vincular():
    if not _bot_auth():
        return jsonify({'ok': False, 'msg': 'No autorizado.'}), 403
    data = request.get_json() or {}
    discord_id   = str(data.get('discord_id', '')).strip()
    discord_name = str(data.get('discord_name', '')).strip()
    code         = str(data.get('code', '')).strip().upper()
    if not discord_id or not code:
        return jsonify({'ok': False, 'msg': 'Faltan datos.'}), 400

    user = User.query.filter_by(recovery_code=code).first()
    if not user:
        return jsonify({'ok': False, 'msg': 'Código incorrecto.'}), 404

    link = DiscordLink.query.filter_by(user_id=user.id).first()
    if link:
        link.discord_id   = discord_id
        link.discord_name = discord_name
    else:
        # Remove any previous link for this discord_id
        DiscordLink.query.filter_by(discord_id=discord_id).delete()
        db.session.add(DiscordLink(user_id=user.id, discord_id=discord_id,
                                   discord_name=discord_name))
    db.session.commit()
    return jsonify({'ok': True, 'name': user.name})


@app.route('/api/discord/pick', methods=['POST'])
@csrf.exempt
def api_discord_pick():
    if not _bot_auth():
        return jsonify({'ok': False, 'msg': 'No autorizado.'}), 403
    data = request.get_json() or {}
    discord_id = str(data.get('discord_id', '')).strip()
    pick       = data.get('pick', '')

    link = DiscordLink.query.filter_by(discord_id=discord_id).first()
    if not link:
        return jsonify({'ok': False, 'msg': 'no_link'}), 404

    if pick not in ('home', 'draw', 'away'):
        return jsonify({'ok': False, 'msg': 'Opción inválida.'}), 400

    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'ok': False, 'msg': 'No hay partido configurado.'}), 400
    try:
        match_data = json.loads(raw)
    except Exception:
        return jsonify({'ok': False, 'msg': 'Error de configuración.'}), 500

    if match_data.get('result'):
        return jsonify({'ok': False, 'msg': 'El partido ya ha terminado.'}), 403

    existing = StreakPick.query.filter_by(
        user_id=link.user_id, match_date=match_data['date']).first()
    if existing:
        existing.pick = pick
    else:
        db.session.add(StreakPick(
            user_id=link.user_id, match_date=match_data['date'], pick=pick))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/discord/pick_status', methods=['POST'])
@csrf.exempt
def api_discord_pick_status():
    if not _bot_auth():
        return jsonify({'ok': False, 'msg': 'No autorizado.'}), 403
    data = request.get_json() or {}
    discord_id = str(data.get('discord_id', '')).strip()
    link = DiscordLink.query.filter_by(discord_id=discord_id).first()
    if not link:
        return jsonify({'pick': None})
    raw = AppConfig.get('streak_match', '')
    if not raw:
        return jsonify({'pick': None})
    try:
        match_data = json.loads(raw)
    except Exception:
        return jsonify({'pick': None})
    sp = StreakPick.query.filter_by(
        user_id=link.user_id, match_date=match_data['date']).first()
    return jsonify({'pick': sp.pick if sp else None})


# ---------------------------------------------------------------------------
# API – leaderboard JSON para Socket.IO polling
# ---------------------------------------------------------------------------

@app.route('/api/leaderboard')
def api_leaderboard():
    return jsonify(get_leaderboard())


@app.route('/api/historial/<int:user_id>')
def api_historial(user_id):
    from models import LeaderboardSnapshot
    snapshots = (LeaderboardSnapshot.query
                 .filter_by(user_id=user_id)
                 .order_by(LeaderboardSnapshot.id.asc())
                 .all())
    return jsonify([{'label': s.label, 'rank': s.rank, 'points': s.total_points}
                    for s in snapshots])


# ---------------------------------------------------------------------------
# Admin – API sync
# ---------------------------------------------------------------------------

@app.route('/admin/sync-api', methods=['POST'])
@admin_required
def admin_sync_api():
    standings = fetcher.fetch_group_standings()
    if standings is None:
        flash('No se pudo conectar con la API o no hay datos de grupos aún.', 'warning')
        return redirect(url_for('admin_panel'))

    board = fetcher.apply_standings_to_db(standings)

    # Also sync knockout matches while we're at it
    knockout_data = fetcher.fetch_knockout_matches()
    if knockout_data:
        fetcher.apply_knockout_matches_to_db(knockout_data)

    socketio.emit('scores_updated', {'leaderboard': board})
    groups_updated = sorted(standings.keys())
    flash(f'Grupos sincronizados: {", ".join(groups_updated)}. '
          f'Puntuaciones recalculadas y enviadas en tiempo real.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/predicciones/eliminatorias/borrar-pick', methods=['POST'])
@csrf.exempt
def clear_knockout_pick():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False}), 401
    data = request.get_json()
    round_id = data.get('round_id')
    match_id = data.get('match_id')
    phase = get_phase()
    is_open = phase.get(f'{round_id}_open', False) or phase.get('bracket_open', False)
    if not is_open:
        return jsonify({'ok': False, 'msg': 'Esta ronda está cerrada.'}), 403
    pred = KnockoutPrediction.query.filter_by(
        user_id=user.id, round_id=round_id, match_id=match_id).first()
    if pred:
        db.session.delete(pred)
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/predicciones/eliminatorias/reset', methods=['POST'])
@csrf.exempt
def reset_knockout_picks():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False}), 401
    KnockoutPrediction.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/build-bracket', methods=['POST'])
@csrf.exempt
@admin_required
def admin_build_bracket():
    r32_data = fetcher.build_r32_from_standings()
    if not r32_data:
        return jsonify({'ok': False, 'msg': 'No hay clasificaciones de grupos en la base de datos todavía.'}), 400
    count = fetcher.apply_r32_to_db(r32_data)
    return jsonify({'ok': True, 'count': count, 'msg': f'{count} partidos de R32 generados desde las clasificaciones.'})


@app.route('/admin/reset-bracket', methods=['POST'])
@csrf.exempt
@admin_required
def admin_reset_bracket():
    KnockoutMatch.query.delete()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/sync-bracket', methods=['POST'])
@admin_required
def admin_sync_bracket():
    knockout_data = fetcher.fetch_knockout_matches()
    if knockout_data is None:
        flash('No se pudo obtener el bracket de la API (datos no disponibles aún).', 'warning')
        return redirect(url_for('admin_panel'))
    fetcher.apply_knockout_matches_to_db(knockout_data)
    rounds_updated = sorted(knockout_data.keys())
    flash(f'Bracket actualizado para: {", ".join(rounds_updated)}.', 'success')
    return redirect(url_for('admin_panel'))


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on('connect')
def on_connect():
    pass


# ---------------------------------------------------------------------------
# Background auto-sync (each hour)
# ---------------------------------------------------------------------------

AUTOSYNC_START = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)  # 19:00 UTC = 21:00 Spain CEST

def _auto_sync_loop():
    socketio.sleep(30)  # let the server finish starting up
    while True:
        now = datetime.now(timezone.utc)
        if now >= AUTOSYNC_START:
            try:
                standings = fetcher.fetch_group_standings()
                if standings:
                    with app.app_context():
                        board = fetcher.apply_standings_to_db(standings)
                    socketio.emit('scores_updated', {'leaderboard': board})
                    logger.info('Auto-sync OK — groups updated: %s', sorted(standings.keys()))
            except Exception as exc:
                logger.error('Auto-sync error: %s', exc)
        else:
            logger.debug('Auto-sync skipped — tournament not started yet')
        socketio.sleep(1800)  # every 30 minutes


def _auto_streak_loop():
    socketio.sleep(60)
    while True:
        try:
            with app.app_context():
                changed = fetcher.auto_update_streak()
                if changed and 'new_match' in changed:
                    # New match detected — signal bot to post immediately
                    AppConfig.set('streak_force_notify', '1')
                    logger.info('New streak match detected, notifying Discord')
                if changed and 'result' in changed:
                    socketio.emit('streak_updated', {'rankings': get_streak_rankings()})
        except Exception as exc:
            logger.error('Auto-streak error: %s', exc)
        socketio.sleep(300)  # every 5 minutes


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        init_db()
    socketio.start_background_task(_auto_sync_loop)
    socketio.start_background_task(_auto_streak_loop)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
