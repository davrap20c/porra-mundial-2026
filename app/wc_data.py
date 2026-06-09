# =========================================================================
# MUNDIAL 2026 - DATOS DE EQUIPOS Y GRUPOS
# Sorteo oficial: 5 de diciembre de 2025, Washington D.C.
# Fuente: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026
# =========================================================================

DEFAULT_GROUPS = {
    'A': ['México', 'Corea del Sur', 'Sudáfrica', 'República Checa'],
    'B': ['Canadá', 'Suiza', 'Qatar', 'Bosnia y Herzegovina'],
    'C': ['Brasil', 'Marruecos', 'Haití', 'Escocia'],
    'D': ['Estados Unidos', 'Paraguay', 'Australia', 'Turquía'],
    'E': ['Alemania', 'Curazao', 'Costa de Marfil', 'Ecuador'],
    'F': ['Países Bajos', 'Japón', 'Suecia', 'Túnez'],
    'G': ['Bélgica', 'Egipto', 'Irán', 'Nueva Zelanda'],
    'H': ['España', 'Cabo Verde', 'Arabia Saudita', 'Uruguay'],
    'I': ['Francia', 'Senegal', 'Irak', 'Noruega'],
    'J': ['Argentina', 'Argelia', 'Austria', 'Jordania'],
    'K': ['Portugal', 'RD Congo', 'Uzbekistán', 'Colombia'],
    'L': ['Inglaterra', 'Croacia', 'Ghana', 'Panamá'],
}

GROUP_NAMES = list(DEFAULT_GROUPS.keys())

TEAM_FLAGS = {
    # Grupo A
    'México':              '🇲🇽',
    'Corea del Sur':       '🇰🇷',
    'Sudáfrica':           '🇿🇦',
    'República Checa':     '🇨🇿',
    # Grupo B
    'Canadá':              '🇨🇦',
    'Suiza':               '🇨🇭',
    'Qatar':               '🇶🇦',
    'Bosnia y Herzegovina':'🇧🇦',
    # Grupo C
    'Brasil':              '🇧🇷',
    'Marruecos':           '🇲🇦',
    'Haití':               '🇭🇹',
    'Escocia':             '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
    # Grupo D
    'Estados Unidos':      '🇺🇸',
    'Paraguay':            '🇵🇾',
    'Australia':           '🇦🇺',
    'Turquía':             '🇹🇷',
    # Grupo E
    'Alemania':            '🇩🇪',
    'Curazao':             '🇨🇼',
    'Costa de Marfil':     '🇨🇮',
    'Ecuador':             '🇪🇨',
    # Grupo F
    'Países Bajos':        '🇳🇱',
    'Japón':               '🇯🇵',
    'Suecia':              '🇸🇪',
    'Túnez':               '🇹🇳',
    # Grupo G
    'Bélgica':             '🇧🇪',
    'Egipto':              '🇪🇬',
    'Irán':                '🇮🇷',
    'Nueva Zelanda':       '🇳🇿',
    # Grupo H
    'España':              '🇪🇸',
    'Cabo Verde':          '🇨🇻',
    'Arabia Saudita':      '🇸🇦',
    'Uruguay':             '🇺🇾',
    # Grupo I
    'Francia':             '🇫🇷',
    'Senegal':             '🇸🇳',
    'Irak':                '🇮🇶',
    'Noruega':             '🇳🇴',
    # Grupo J
    'Argentina':           '🇦🇷',
    'Argelia':             '🇩🇿',
    'Austria':             '🇦🇹',
    'Jordania':            '🇯🇴',
    # Grupo K
    'Portugal':            '🇵🇹',
    'RD Congo':            '🇨🇩',
    'Uzbekistán':          '🇺🇿',
    'Colombia':            '🇨🇴',
    # Grupo L
    'Inglaterra':          '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
    'Croacia':             '🇭🇷',
    'Ghana':               '🇬🇭',
    'Panamá':              '🇵🇦',
}


def flag(team):
    return TEAM_FLAGS.get(team, '🏳️')

ALL_TEAMS = sorted([team for teams in DEFAULT_GROUPS.values() for team in teams])

SPECIAL_CATEGORIES = [
    {'id': 'champion',      'label': 'Campeón del Mundial',           'type': 'team',   'icon': 'bi-trophy-fill',    'points': 500},
    {'id': 'runner_up',     'label': 'Subcampeón',                    'type': 'team',   'icon': 'bi-award-fill',     'points': 500},
    {'id': 'third_place',   'label': 'Tercer puesto',                 'type': 'team',   'icon': 'bi-award',          'points': 500},
    {'id': 'top_scorer',    'label': 'Máximo goleador',               'type': 'player', 'icon': 'bi-bullseye',       'points': 500},
    {'id': 'top_assists',   'label': 'Máximo asistente',              'type': 'player', 'icon': 'bi-send-fill',      'points': 500},
    {'id': 'best_player',   'label': 'Balón de Oro (mejor jugador)',  'type': 'player', 'icon': 'bi-star-fill',      'points': 500},
    {'id': 'best_keeper',   'label': 'Guante de Oro (mejor portero)', 'type': 'player', 'icon': 'bi-shield-fill',    'points': 500},
    {'id': 'best_young',    'label': 'Mejor jugador joven',           'type': 'player', 'icon': 'bi-lightning-fill', 'points': 500},
    {'id': 'surprise_team', 'label': 'Equipo sorpresa del torneo',    'type': 'team',   'icon': 'bi-stars',          'points': 500},
]

ROUNDS = [
    {'id': 'r32', 'name': 'Ronda de 32', 'matches': 16},
    {'id': 'r16', 'name': 'Octavos de Final', 'matches': 8},
    {'id': 'qf',  'name': 'Cuartos de Final', 'matches': 4},
    {'id': 'sf',  'name': 'Semifinales', 'matches': 2},
    {'id': 'tp',  'name': 'Tercer Puesto', 'matches': 1},
    {'id': 'final', 'name': 'Final', 'matches': 1},
]

PHASE_CONFIG = {
    'groups_open':   {'label': 'Predicciones de Grupos',             'default': False},
    'specials_open': {'label': 'Predicciones Especiales',            'default': False},
    'bracket_open':  {'label': 'Predicciones Eliminatorias (todas)', 'default': False},
    'r32_open':      {'label': 'Predicciones Ronda de 32',           'default': False},
    'r16_open':      {'label': 'Predicciones Octavos',               'default': False},
    'qf_open':       {'label': 'Predicciones Cuartos',               'default': False},
    'sf_open':       {'label': 'Predicciones Semifinales',           'default': False},
    'tp_open':       {'label': 'Predicciones Tercer Puesto',         'default': False},
    'final_open':    {'label': 'Predicciones Final',                 'default': False},
}

# Official WC 2026 R32 pairings from the December 2025 draw.
# Each tuple: (match_id, group_A, pos_A, group_B, pos_B)
# pos 1=winner, 2=runner-up, 3=third-place.
# For 3rd-place slots the group shown is only the placeholder used before real standings
# arrive — the actual matchup depends on which 8 of 12 third-place teams qualify.
# Placeholder groups were chosen so all 8 are distinct and satisfy the FIFA constraint.
R32_SLOTS = [
    (1,  'E', 1, 'A', 3),   # 1E vs 3(ABCDF)  — placeholder: 3A
    (2,  'I', 1, 'G', 3),   # 1I vs 3(CDFGH)  — placeholder: 3G
    (3,  'A', 2, 'B', 2),   # 2A vs 2B
    (4,  'F', 1, 'C', 2),   # 1F vs 2C
    (5,  'K', 2, 'L', 2),   # 2K vs 2L
    (6,  'H', 1, 'J', 2),   # 1H vs 2J
    (7,  'D', 1, 'B', 3),   # 1D vs 3(BEFIJ)  — placeholder: 3B
    (8,  'G', 1, 'H', 3),   # 1G vs 3(AEHIJ)  — placeholder: 3H
    (9,  'C', 1, 'F', 2),   # 1C vs 2F
    (10, 'E', 2, 'I', 2),   # 2E vs 2I
    (11, 'A', 1, 'C', 3),   # 1A vs 3(CEFHI)  — placeholder: 3C
    (12, 'L', 1, 'K', 3),   # 1L vs 3(EHIJK)  — placeholder: 3K
    (13, 'J', 1, 'H', 2),   # 1J vs 2H
    (14, 'D', 2, 'G', 2),   # 2D vs 2G
    (15, 'B', 1, 'J', 3),   # 1B vs 3(EFGIJ)  — placeholder: 3J
    (16, 'K', 1, 'D', 3),   # 1K vs 3(DEIJL)  — placeholder: 3D
]

# Number of matches per knockout round
ROUND_MATCH_COUNTS = {
    'r32': 16, 'r16': 8, 'qf': 4, 'sf': 2, 'tp': 1, 'final': 1,
}

# Which match feeds into which: BRACKET_TREE[round][match_id] = (next_round, next_match_id, slot)
# slot 0 = team1, slot 1 = team2 of the parent match
BRACKET_TREE = {
    'r32': {i: ('r16',   (i + 1) // 2, (i - 1) % 2) for i in range(1, 17)},
    'r16': {i: ('qf',    (i + 1) // 2, (i - 1) % 2) for i in range(1, 9)},
    'qf':  {i: ('sf',    (i + 1) // 2, (i - 1) % 2) for i in range(1, 5)},
    'sf':  {1: ('final', 1, 0), 2: ('final', 1, 1)},
}
# SF losers go to the 3rd-place match
SF_LOSER_TO_TP = {1: ('tp', 1, 0), 2: ('tp', 1, 1)}
