"""
Auto-fetcher for WC 2026 standings and knockout matches from football-data.org v4 API.
Runs as a background task every hour; also callable manually from admin.
"""
import os
import logging
import requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from models import db, ActualGroupStanding, KnockoutMatch, AppConfig, StreakPick
from scoring import recalculate_all_scores, get_leaderboard

logger = logging.getLogger(__name__)

API_KEY = os.environ.get('FOOTBALL_API_KEY', '')
API_BASE = 'https://api.football-data.org/v4'
COMPETITION = 'WC'

# football-data.org English names → our Spanish names in the DB
TEAM_NAME_MAP = {
    'Mexico':                        'México',
    'South Korea':                   'Corea del Sur',
    'Korea Republic':                'Corea del Sur',
    'South Africa':                  'Sudáfrica',
    'Czechia':                       'República Checa',
    'Czech Republic':                'República Checa',
    'Canada':                        'Canadá',
    'Switzerland':                   'Suiza',
    'Qatar':                         'Qatar',
    'Bosnia and Herzegovina':        'Bosnia y Herzegovina',
    'Bosnia-Herzegovina':            'Bosnia y Herzegovina',
    'Brazil':                        'Brasil',
    'Morocco':                       'Marruecos',
    'Haiti':                         'Haití',
    'Scotland':                      'Escocia',
    'United States':                 'Estados Unidos',
    'USA':                           'Estados Unidos',
    'Paraguay':                      'Paraguay',
    'Australia':                     'Australia',
    'Turkey':                        'Turquía',
    'Türkiye':                       'Turquía',
    'Germany':                       'Alemania',
    'Curaçao':                       'Curazao',
    'Curacao':                       'Curazao',
    "Côte d'Ivoire":                 'Costa de Marfil',
    'Ivory Coast':                   'Costa de Marfil',
    'Ecuador':                       'Ecuador',
    'Netherlands':                   'Países Bajos',
    'Japan':                         'Japón',
    'Sweden':                        'Suecia',
    'Tunisia':                       'Túnez',
    'Belgium':                       'Bélgica',
    'Egypt':                         'Egipto',
    'Iran':                          'Irán',
    'IR Iran':                       'Irán',
    'New Zealand':                   'Nueva Zelanda',
    'Spain':                         'España',
    'Cape Verde':                    'Cabo Verde',
    'Cape Verde Islands':            'Cabo Verde',
    'Saudi Arabia':                  'Arabia Saudita',
    'Uruguay':                       'Uruguay',
    'France':                        'Francia',
    'Senegal':                       'Senegal',
    'Iraq':                          'Irak',
    'Norway':                        'Noruega',
    'Algeria':                       'Argelia',
    'Algeria (DZ)':                  'Argelia',
    'Austria':                       'Austria',
    'Jordan':                        'Jordania',
    'Portugal':                      'Portugal',
    'DR Congo':                      'RD Congo',
    'Congo DR':                      'RD Congo',
    'Congo, DR':                     'RD Congo',
    'Democratic Republic of Congo':  'RD Congo',
    'Uzbekistan':                    'Uzbekistán',
    'Colombia':                      'Colombia',
    'England':                       'Inglaterra',
    'Croatia':                       'Croacia',
    'Ghana':                         'Ghana',
    'Panama':                        'Panamá',
    'Argentina':                     'Argentina',
}


def _map_team(api_name: str) -> str:
    """Return our DB name for a team, falling back to the API name if unknown."""
    mapped = TEAM_NAME_MAP.get(api_name)
    if not mapped:
        logger.warning('Unknown team name from API: %r — using as-is', api_name)
    return mapped or api_name


def fetch_group_standings() -> dict | None:
    """
    Fetch current WC group standings from the API.
    Returns {group_letter: [team1, team2, team3, team4]} ordered by position,
    or None if the request fails or no data is available yet.
    """
    if not API_KEY:
        logger.warning('FOOTBALL_API_KEY not set — auto-sync disabled')
        return None

    try:
        resp = requests.get(
            f'{API_BASE}/competitions/{COMPETITION}/standings',
            headers={'X-Auth-Token': API_KEY},
            timeout=15,
        )
        if resp.status_code == 404:
            logger.info('WC 2026 standings endpoint returned 404 — tournament may not have started')
            return None
        if resp.status_code == 429:
            logger.warning('API rate limit hit — will retry next cycle')
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error('football-data.org request failed: %s', exc)
        return None

    data = resp.json()
    standings = data.get('standings', [])
    result = {}

    for group in standings:
        if group.get('type') != 'TOTAL':
            continue
        raw_group = group.get('group', '')  # "Group A" or "GROUP_A"
        # Normalise: take the last token and uppercase it → "A", "B", …
        parts = raw_group.replace('_', ' ').split()
        if not parts:
            continue
        letter = parts[-1].upper()

        table = sorted(group.get('table', []), key=lambda r: r.get('position', 99))
        if len(table) != 4:
            continue

        # Only include groups where at least one game has been played
        if all(row.get('playedGames', 0) == 0 for row in table):
            continue

        result[letter] = [_map_team(row['team']['name']) for row in table]

    return result or None


def apply_standings_to_db(standings: dict) -> list:
    """
    Write fetched standings into ActualGroupStanding and recalculate.
    Must be called inside an app context.
    Returns the updated leaderboard list.
    """
    for letter, teams in standings.items():
        ActualGroupStanding.query.filter_by(group_name=letter).delete()
        for pos, team in enumerate(teams, 1):
            db.session.add(ActualGroupStanding(
                group_name=letter, team_name=team, position=pos))

    AppConfig.set('last_api_sync', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    db.session.commit()

    recalculate_all_scores()
    return get_leaderboard()


KNOCKOUT_STAGE_MAP = {
    'ROUND_OF_32':    ('r32',   16),
    'ROUND_OF_16':    ('r16',   8),
    'QUARTER_FINALS': ('qf',    4),
    'SEMI_FINALS':    ('sf',    2),
    'THIRD_PLACE':    ('tp',    1),
    'FINAL':          ('final', 1),
}


def build_r32_from_standings() -> dict[str, tuple]:
    """
    Generate R32 KnockoutMatch records from ActualGroupStanding already in DB.
    Falls back to DEFAULT_GROUPS list order for groups with no real standings yet.
    Returns {match_id: (team1, team2)} for matches that could be resolved.
    3rd-place slots (matches 13-16) are skipped — must be filled manually.
    """
    from wc_data import R32_SLOTS, DEFAULT_GROUPS

    # Build standings lookup: {group_letter: {position: team_name}}
    standings: dict[str, dict[int, str]] = {}
    for s in ActualGroupStanding.query.all():
        standings.setdefault(s.group_name, {})[s.position] = s.team_name

    # For groups with no real standings yet, use DEFAULT_GROUPS list order as placeholder
    for letter, teams in DEFAULT_GROUPS.items():
        if letter not in standings:
            standings[letter] = {i + 1: team for i, team in enumerate(teams)}

    result = {}
    for slot in R32_SLOTS:
        match_id, grp_a, pos_a, grp_b, pos_b = slot
        team1 = standings.get(grp_a, {}).get(pos_a, '')
        team2 = standings.get(grp_b, {}).get(pos_b, '')
        if team1 or team2:
            result[match_id] = (team1, team2)

    return result


def apply_r32_to_db(r32_data: dict) -> int:
    """
    Write generated R32 matches to KnockoutMatch.
    Only overwrites matches that don't have a winner yet.
    Returns number of matches created/updated.
    """
    count = 0
    for match_id, (team1, team2) in r32_data.items():
        existing = KnockoutMatch.query.filter_by(round_id='r32', match_id=match_id).first()
        if existing:
            if existing.winner:
                continue  # result already entered, don't overwrite
            existing.team1 = team1
            existing.team2 = team2
        else:
            db.session.add(KnockoutMatch(
                round_id='r32', match_id=match_id, team1=team1, team2=team2))
        count += 1
    db.session.commit()
    return count


def fetch_knockout_matches() -> dict | None:
    """
    Fetch knockout match pairings + results from the API.
    Returns {round_id: {match_id: (team1, team2, winner_or_None)}} or None if fails/no data.
    """
    if not API_KEY:
        return None

    try:
        resp = requests.get(
            f'{API_BASE}/competitions/{COMPETITION}/matches',
            params={'stage': ','.join(KNOCKOUT_STAGE_MAP.keys())},
            headers={'X-Auth-Token': API_KEY},
            timeout=15,
        )
        if resp.status_code in (404, 400):
            logger.info('Knockout matches endpoint returned %s — data not available yet', resp.status_code)
            return None
        if resp.status_code == 429:
            logger.warning('API rate limit hit for knockout fetch')
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error('football-data.org knockout request failed: %s', exc)
        return None

    matches_data = resp.json().get('matches', [])
    by_stage = defaultdict(list)
    for m in matches_data:
        stage = m.get('stage', '')
        if stage in KNOCKOUT_STAGE_MAP:
            by_stage[stage].append(m)

    result = {}
    for stage, stage_matches in by_stage.items():
        round_id, expected_count = KNOCKOUT_STAGE_MAP[stage]
        stage_matches.sort(key=lambda m: (m.get('utcDate', ''), m.get('id', 0)))
        round_result = {}
        for idx, m in enumerate(stage_matches[:expected_count], 1):
            home_raw = (m['homeTeam'] or {}).get('name', '') or ''
            away_raw = (m['awayTeam'] or {}).get('name', '') or ''
            team1 = _map_team(home_raw) if home_raw else ''
            team2 = _map_team(away_raw) if away_raw else ''

            winner = None
            if m.get('status') == 'FINISHED' and team1 and team2:
                score = m.get('score', {})
                # Check penalties first (they override FT for determining match winner)
                pen = score.get('penalties', {})
                if pen and pen.get('home') is not None:
                    winner = team1 if (pen['home'] or 0) > (pen['away'] or 0) else team2
                else:
                    ft = score.get('fullTime', {})
                    h, a = ft.get('home'), ft.get('away')
                    if h is not None and a is not None:
                        winner = team1 if h > a else team2

            if team1 or team2:
                round_result[idx] = (team1, team2, winner)
        if round_result:
            result[round_id] = round_result

    return result or None


def apply_knockout_matches_to_db(knockout_data: dict) -> None:
    """Write fetched knockout match data into the KnockoutMatch table."""
    for round_id, matches in knockout_data.items():
        for match_id, (team1, team2, winner) in matches.items():
            existing = KnockoutMatch.query.filter_by(
                round_id=round_id, match_id=match_id).first()
            if existing:
                if team1: existing.team1 = team1
                if team2: existing.team2 = team2
                if winner and not existing.winner:
                    existing.winner = winner
            else:
                db.session.add(KnockoutMatch(
                    round_id=round_id, match_id=match_id,
                    team1=team1, team2=team2, winner=winner))
    db.session.commit()


_upcoming_cache: dict = {'data': None, 'ts': 0.0}

_TTL_ACTIVE  = 60    # 1 min when a match is live or starting soon
_TTL_IDLE    = 3600  # 1 hour when no action


def _cache_ttl(data: list | None) -> int:
    """60s if any match is live/paused, starting soon, or finished within 4h. Else 1h."""
    if not data:
        return _TTL_IDLE
    now = datetime.now(timezone.utc)
    for m in data:
        if m['status'] in ('IN_PLAY', 'PAUSED'):
            return _TTL_ACTIVE
        try:
            dt = datetime.fromisoformat(m['date'].replace('Z', '+00:00'))
            secs = (now - dt).total_seconds()
            # Active window: 2h before kickoff until 4h after kickoff
            if -7200 < secs < 14400:
                return _TTL_ACTIVE
        except Exception:
            pass
    return _TTL_IDLE


def fetch_upcoming_matches(days_ahead: int = 14) -> list | None:
    """
    Return WC matches scheduled (or live) in the next `days_ahead` days.
    Each entry: {date, home, away, stage, group, status, score_home, score_away}

    Cache strategy:
    - 1 min TTL while a match is live or kicks off within 2h
    - 1 hour TTL otherwise
    - On API error or rate-limit, returns stale cached data (score stays visible)
    - Preserves last known score if the API reverts a match to TIMED mid-game
    """
    import time
    if not API_KEY:
        return None

    now_ts = time.monotonic()
    cached = _upcoming_cache
    ttl = _cache_ttl(cached['data'])
    if cached['data'] is not None and (now_ts - cached['ts']) < ttl:
        return cached['data']

    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=4)).strftime('%Y-%m-%d')
    date_to   = (now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    try:
        resp = requests.get(
            f'{API_BASE}/competitions/{COMPETITION}/matches',
            params={'dateFrom': date_from, 'dateTo': date_to},
            headers={'X-Auth-Token': API_KEY},
            timeout=10,
        )
        if resp.status_code in (400, 404):
            return cached['data']
        if resp.status_code == 429:
            logger.warning('API rate limit — returning cached upcoming matches')
            return cached['data']
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error('upcoming matches request failed: %s', exc)
        return cached['data']

    # Build lookup of old scores to preserve them if API regresses to TIMED
    old_scores: dict = {}
    if cached['data']:
        for m in cached['data']:
            if m['score_home'] is not None:
                old_scores[(m['home'], m['away'], m['date'][:10])] = (
                    m['score_home'], m['score_away'], m['status'])

    result = []
    for m in resp.json().get('matches', []):
        home_raw  = ((m.get('homeTeam') or {}).get('name') or '')
        away_raw  = ((m.get('awayTeam') or {}).get('name') or '')
        status    = m.get('status', '')
        score_obj = m.get('score') or {}
        ft        = score_obj.get('fullTime') or {}
        ht        = score_obj.get('halfTime') or {}
        score_h   = ft.get('home')
        score_a   = ft.get('away')
        # At halftime the API populates halfTime but not fullTime
        if score_h is None and status == 'PAUSED':
            score_h = ht.get('home')
            score_a = ht.get('away')
        group_raw = m.get('group') or ''
        home      = _map_team(home_raw) if home_raw else ''
        away      = _map_team(away_raw) if away_raw else ''

        # Preserve score + status when API reverts to TIMED after showing a score
        if score_h is None and status == 'TIMED':
            key = (home, away, m['utcDate'][:10])
            if key in old_scores:
                score_h, score_a, status = old_scores[key]

        result.append({
            'date':       m['utcDate'],
            'home':       home,
            'away':       away,
            'stage':      m.get('stage', ''),
            'group':      group_raw.replace('GROUP_', ''),
            'status':     status,
            'score_home': score_h,
            'score_away': score_a,
        })

    if result:
        _upcoming_cache['data'] = result
        _upcoming_cache['ts']   = now_ts
    return result or cached['data']


def auto_update_streak() -> dict | None:
    """
    Check live/recent matches and auto-set streak_match + result.
    Returns a dict with what changed: {'new_match': {...}, 'result': 'home'|...} or None.
    Must be called inside an app context.
    """
    import json
    matches = fetch_upcoming_matches(days_ahead=1)
    if not matches:
        return None

    changed = {}

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # Find a live or very recently finished group-stage match
    live = next((m for m in matches
                 if m['stage'] == 'GROUP_STAGE'
                 and m['status'] in ('IN_PLAY', 'PAUSED')), None)
    finished_recent = [
        m for m in matches
        if m['stage'] == 'GROUP_STAGE'
        and m['status'] == 'FINISHED'
        and m['score_home'] is not None
    ]
    finished_recent.sort(key=lambda m: m['date'], reverse=True)

    # Scheduled matches today (show in advance so users can predict before kickoff)
    scheduled_today = [
        m for m in matches
        if m['stage'] == 'GROUP_STAGE'
        and m['status'] in ('TIMED', 'SCHEDULED')
        and m['date'][:10] == today
    ]
    scheduled_today.sort(key=lambda m: m['date'])

    raw = AppConfig.get('streak_match', '')
    current = {}
    if raw:
        try:
            current = json.loads(raw)
        except Exception:
            pass

    # Next scheduled today that hasn't been used yet as streak match
    resolved_raw = AppConfig.get('streak_resolved_dates', '[]')
    try:
        resolved_dates = set(json.loads(resolved_raw))
    except Exception:
        resolved_dates = set()

    # Scheduled today that aren't already resolved
    next_scheduled = next(
        (m for m in scheduled_today if m['date'][:10] not in resolved_dates),
        None
    )

    # Priority: live > next scheduled today > most recently finished (unresolved)
    next_finished = next(
        (m for m in finished_recent if m['date'][:10] not in resolved_dates),
        None
    )
    target = live or next_scheduled or next_finished
    if target:
        match_date = target['date'][:10]
        is_same = (current.get('date') == match_date
                   and current.get('home') == target['home']
                   and current.get('away') == target['away'])
        if not is_same:
            new_match = {
                'date': match_date,
                'kickoff': target['date'],  # full ISO datetime for vote-locking
                'home': target['home'],
                'away': target['away'],
                'result': None,
            }
            AppConfig.set('streak_match', json.dumps(new_match, ensure_ascii=False))
            current = new_match
            changed['new_match'] = new_match
            logger.info('Auto streak match set: %s vs %s', target['home'], target['away'])

    # Persist score as soon as the API returns one (halftime or full-time)
    if current and current.get('score_home') is None:
        all_with_score = [
            m for m in matches
            if m['stage'] == 'GROUP_STAGE'
            and m['score_home'] is not None
            and m['date'][:10] == current.get('date')
            and m['home'] == current.get('home')
            and m['away'] == current.get('away')
        ]
        if all_with_score:
            api_match = all_with_score[0]
            current['score_home'] = api_match['score_home']
            current['score_away'] = api_match['score_away']
            AppConfig.set('streak_match', json.dumps(current, ensure_ascii=False))
            logger.info('Streak score persisted: %s-%s', current['score_home'], current['score_away'])

    # Auto-set result when finished
    if current and not current.get('result') and finished_recent:
        match = next(
            (m for m in finished_recent
             if m['date'][:10] == current.get('date')
             and m['home'] == current.get('home')
             and m['away'] == current.get('away')),
            None
        )
        if match and match['score_home'] is not None and match['score_away'] is not None:
            h, a = match['score_home'], match['score_away']
            result = 'home' if h > a else ('away' if a > h else 'draw')
            current['result'] = result
            current['score_home'] = h
            current['score_away'] = a
            AppConfig.set('streak_match', json.dumps(current, ensure_ascii=False))

            # Register resolved date so streak points can be computed
            resolved_raw = AppConfig.get('streak_resolved_dates', '[]')
            try:
                resolved_dates = json.loads(resolved_raw)
            except Exception:
                resolved_dates = []
            if current['date'] not in resolved_dates:
                resolved_dates.append(current['date'])
                resolved_dates.sort()
                AppConfig.set('streak_resolved_dates', json.dumps(resolved_dates))

            picks = StreakPick.query.filter_by(match_date=current['date']).all()
            for p in picks:
                p.correct = (p.pick == result)
            db.session.commit()
            changed['result'] = result
            logger.info('Auto streak result set: %s', result)

    return changed or None


def fetch_and_apply(app) -> list | None:
    """
    Full cycle: fetch standings → write to DB → recalculate.
    Returns leaderboard list (for emitting) or None if nothing changed.
    """
    standings = fetch_group_standings()
    if not standings:
        return None

    with app.app_context():
        logger.info('Applying standings for groups: %s', sorted(standings.keys()))
        return apply_standings_to_db(standings)
