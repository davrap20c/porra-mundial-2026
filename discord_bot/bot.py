import os
import logging
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BOT_TOKEN  = os.environ['DISCORD_BOT_TOKEN']
CHANNEL_ID = int(os.environ['DISCORD_CHANNEL_ID'])
GUILD_ID   = int(os.environ['DISCORD_GUILD_ID'])
APP_URL    = os.environ.get('APP_URL', 'http://web:5000')
BOT_SECRET = os.environ['BOT_SECRET']

intents = discord.Intents.default()
bot     = discord.Client(intents=intents)
tree    = app_commands.CommandTree(bot)

# ── State ─────────────────────────────────────────────────────────────────────
_last_match_key  = None   # "YYYY-MM-DD|home|away"
_last_result     = None   # 'home'|'draw'|'away'|None
_pick_message_id = None   # id of the active pick message


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _api_post(path: str, payload: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f'{APP_URL}{path}',
            json=payload,
            headers={'X-Bot-Secret': BOT_SECRET},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            return await r.json()


async def _api_get(path: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f'{APP_URL}{path}',
            headers={'X-Bot-Secret': BOT_SECRET},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            return await r.json()


PICK_LABELS = {'home': '🏠 Local', 'draw': '🤝 Empate', 'away': '✈️ Visitante'}


# ── Pick buttons ──────────────────────────────────────────────────────────────
def _bar(pct: int, width: int = 10) -> str:
    filled = round(pct * width / 100)
    return '█' * filled + '░' * (width - filled)


class PickView(discord.ui.View):
    def __init__(self, home: str, away: str):
        super().__init__(timeout=None)
        for pick, label, style in [
            ('home', f'🏠 {home}',  discord.ButtonStyle.primary),
            ('draw', '🤝 Empate',    discord.ButtonStyle.secondary),
            ('away', f'✈️ {away}',  discord.ButtonStyle.danger),
        ]:
            btn = discord.ui.Button(label=label, style=style, custom_id=f'streak_{pick}')
            btn.callback = self._make_cb(pick)
            self.add_item(btn)

        btn_votes = discord.ui.Button(
            label='📊 Ver votos', style=discord.ButtonStyle.secondary,
            custom_id='streak_votes', row=1)
        btn_votes.callback = self._cb_votes
        self.add_item(btn_votes)

        btn_rank = discord.ui.Button(
            label='🏆 Clasificación', style=discord.ButtonStyle.secondary,
            custom_id='streak_rank', row=1)
        btn_rank.callback = self._cb_rank
        self.add_item(btn_rank)

    def _make_cb(self, pick: str):
        async def cb(interaction: discord.Interaction):
            data = await _api_post('/api/discord/pick', {
                'discord_id': str(interaction.user.id),
                'pick': pick,
            })
            if data.get('ok'):
                await interaction.response.send_message(
                    f'✅ Guardado: **{PICK_LABELS[pick]}**', ephemeral=True)
            elif 'no_link' in str(data.get('msg', '')):
                await interaction.response.send_message(
                    '❌ No tienes cuenta vinculada.\n'
                    'Usa `/vincular TUCODIGO` (el código de 8 letras de tu perfil en la porra).',
                    ephemeral=True)
            else:
                await interaction.response.send_message(
                    f'❌ {data.get("msg", "Error")}', ephemeral=True)
        return cb

    async def _cb_votes(self, interaction: discord.Interaction):
        data = await _api_get('/api/streak/votes')
        if not data.get('match'):
            await interaction.response.send_message('⏳ No hay partido configurado.', ephemeral=True)
            return
        m     = data['match']
        pct   = data['pct']
        total = data['total']
        home_label = m['home']
        away_label = m['away']
        lines = [
            f'**{m["home"]} vs {m["away"]}** — {total} voto{"s" if total != 1 else ""}',
            '',
            f'🏠 **{home_label}**  {_bar(pct["home"])}  {pct["home"]}%  ({data["counts"]["home"]})',
            f'🤝 **Empate**        {_bar(pct["draw"])}  {pct["draw"]}%  ({data["counts"]["draw"]})',
            f'✈️ **{away_label}**  {_bar(pct["away"])}  {pct["away"]}%  ({data["counts"]["away"]})',
        ]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    async def _cb_rank(self, interaction: discord.Interaction):
        data = await _api_get('/api/streak/rankings')
        rankings = data.get('rankings', [])
        if not rankings:
            await interaction.response.send_message('📊 Aún no hay rachas registradas.', ephemeral=True)
            return
        medals = ['🥇', '🥈', '🥉']
        lines = []
        for i, r in enumerate(rankings[:10]):
            prefix = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f'{prefix} **{r["name"]}** — 🔥{r["current"]}  _(máx {r["max"]})_')
        embed = discord.Embed(
            title='🏆 Clasificación — Racha del Día',
            description='\n'.join(lines),
            color=0xffc107,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Commands ──────────────────────────────────────────────────────────────────
@tree.command(name='vincular', description='Vincula tu cuenta de la porra con Discord')
@app_commands.describe(codigo='Código de 8 caracteres que ves en tu perfil de la porra')
async def cmd_vincular(interaction: discord.Interaction, codigo: str):
    data = await _api_post('/api/discord/vincular', {
        'discord_id':   str(interaction.user.id),
        'discord_name': str(interaction.user),
        'code':         codigo.upper().strip(),
    })
    if data.get('ok'):
        await interaction.response.send_message(
            f'✅ Vinculado como **{data["name"]}**. '
            'Tus picks en Discord se guardarán en tu cuenta.',
            ephemeral=True)
    else:
        await interaction.response.send_message(
            f'❌ {data.get("msg", "Código incorrecto.")}', ephemeral=True)


@tree.command(name='clasificacion', description='Muestra el ranking de la Racha del Día')
async def cmd_clasificacion(interaction: discord.Interaction):
    data = await _api_get('/api/streak/rankings')
    rankings = data.get('rankings', [])
    if not rankings:
        await interaction.response.send_message(
            '📊 Aún no hay rachas registradas.', ephemeral=False)
        return

    medals = ['🥇', '🥈', '🥉']
    lines = []
    for i, r in enumerate(rankings[:15]):
        prefix = medals[i] if i < 3 else f'`{i+1}.`'
        lines.append(f'{prefix} **{r["name"]}** — 🔥 {r["current"]}  _(máx {r["max"]})_')

    embed = discord.Embed(
        title='🏆 Clasificación — Racha del Día',
        description='\n'.join(lines),
        color=0xffc107,
    )
    embed.set_footer(text='Racha actual · entre paréntesis la racha máxima histórica')
    await interaction.response.send_message(embed=embed)


@tree.command(name='estado', description='Muestra el partido del día y tu predicción')
async def cmd_estado(interaction: discord.Interaction):
    data = await _api_get('/api/streak')
    match = data.get('match')
    if not match:
        await interaction.response.send_message(
            '⏳ No hay partido configurado hoy.', ephemeral=True)
        return

    # Check if this discord user has a pick saved
    pick_data = await _api_post('/api/discord/pick_status', {
        'discord_id': str(interaction.user.id),
    })
    pick   = pick_data.get('pick')
    result = match.get('result')

    lines = [f'**{match["home"]} vs {match["away"]}**']
    if pick:
        lines.append(f'Tu predicción: **{PICK_LABELS[pick]}**')
        if result:
            lines.append('✅ ¡Acertaste!' if pick == result else '❌ Fallaste.')
        else:
            lines.append('_El partido aún no ha terminado._')
    else:
        lines.append('No has predicho aún — usa los botones del canal.')
    streak = data.get('my_streak', {})
    if streak.get('current'):
        lines.append(f'Tu racha actual: 🔥{streak["current"]}')

    await interaction.response.send_message('\n'.join(lines), ephemeral=True)


# ── Polling loop ──────────────────────────────────────────────────────────────
@tasks.loop(minutes=2)
async def poll_streak():
    global _last_match_key, _last_result, _pick_message_id

    try:
        data = await _api_get('/api/streak')
    except Exception as exc:
        log.warning('poll_streak error: %s', exc)
        return

    # ── Send recovery DMs if admin requested ─────────────────────────────────
    if data.get('send_recovery_dms'):
        try:
            codes_data = await _api_get('/api/discord/recovery-codes')
            sent = 0
            for u in codes_data.get('users', []):
                try:
                    member = await bot.fetch_user(int(u['discord_id']))
                    await member.send(
                        f'👋 Hola **{u["name"]}**!\n\n'
                        f'Tu clave de recuperación para la **Porra Mundial 2026** es:\n'
                        f'```\n{u["recovery_code"]}\n```\n'
                        f'Úsala en la web si pierdes acceso a tu cuenta.'
                    )
                    sent += 1
                except Exception as e:
                    log.warning('No se pudo enviar DM a %s: %s', u["discord_id"], e)
            log.info('Recovery DMs enviados: %d/%d', sent, len(codes_data.get('users', [])))
        except Exception as exc:
            log.warning('Error enviando recovery DMs: %s', exc)

    match = data.get('match')
    if not match:
        return

    match_key    = f'{match["date"]}|{match["home"]}|{match["away"]}'
    result       = match.get('result')
    force_notify = data.get('force_notify', False)
    channel      = bot.get_channel(CHANNEL_ID)
    if not channel:
        log.warning('Channel %s not found', CHANNEL_ID)
        return

    # ── New match (or forced by admin) ────────────────────────────────────────
    if match_key != _last_match_key or force_notify:
        _last_match_key  = match_key
        _last_result     = result
        _pick_message_id = None

        embed = discord.Embed(
            title='🔥 Partido del Día — Racha',
            description=(
                f'**{match["home"]}** vs **{match["away"]}**\n\n'
                '¿Quién gana? Pulsa un botón para hacer tu predicción.\n'
                'Acierta y mantén tu 🔥 racha.'
            ),
            color=0xffc107,
        )
        view = PickView(match['home'], match['away'])
        guild = bot.get_guild(GUILD_ID)
        role  = discord.utils.get(guild.roles, name='MUNDIAL SIUUUU') if guild else None
        mention = role.mention if role else '@here'
        msg  = await channel.send(mention, embed=embed, view=view)
        _pick_message_id = msg.id
        if force_notify:
            await _api_post('/api/streak/clear-notify', {'match_key': match_key})
        else:
            await _api_post('/api/streak/mark-notified', {'match_key': match_key})
        return

    # ── Result just set ───────────────────────────────────────────────────────
    if result and result != _last_result:
        _last_result = result

        rankings = data.get('rankings', [])
        medals   = ['🥇', '🥈', '🥉']
        top_lines = [
            f'{medals[i] if i < 3 else f"{i+1}."} **{r["name"]}** — 🔥{r["current"]} (máx {r["max"]})'
            for i, r in enumerate(rankings[:5])
        ] if rankings else ['_Sin rachas todavía._']

        embed = discord.Embed(
            title='📊 Resultado — Racha del Día',
            description=(
                f'**{match["home"]}** vs **{match["away"]}**\n'
                f'Resultado: **{PICK_LABELS[result]}**'
            ),
            color=0x28a745,
        )
        embed.add_field(
            name='🏆 Ranking de rachas', value='\n'.join(top_lines), inline=False)
        await channel.send(embed=embed)


@poll_streak.before_loop
async def before_poll():
    await bot.wait_until_ready()
    # Restore last notified key so we don't re-post on restart
    global _last_match_key
    try:
        data = await _api_get('/api/streak')
        _last_match_key = data.get('last_notified_key') or _last_match_key
        log.info('Restored last notified match key: %s', _last_match_key)
    except Exception as exc:
        log.warning('Could not restore last notified key: %s', exc)


@bot.event
async def on_ready():
    log.info('Bot conectado como %s (id %s)', bot.user, bot.user.id)
    guild = discord.Object(id=GUILD_ID)
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    log.info('Slash commands sincronizados al servidor %s', GUILD_ID)
    poll_streak.start()


bot.run(BOT_TOKEN)
