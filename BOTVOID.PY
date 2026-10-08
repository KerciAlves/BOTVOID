# ============================================================
# VOIDHELPER - BOT DISCORD
# Versão otimizada para hospedagem de baixo consumo
# ============================================================

import os
import io
import re
import gc
import time
import sqlite3
import asyncio
import hashlib
from collections import defaultdict, deque
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# Canal antigo de reações
CANAL_REACOES_ID = 1556998399461691443

# Canal da loja Fortnite
CANAL_LOJA_ID = 1214658145243234324

# API Fortnite
FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

# Idioma
IDIOMA = "pt-BR"

# Intervalo da loja
INTERVALO_VERIFICACAO = 300

# Banco
DATABASE_FILE = "voidhelper.db"

# Estado da loja
SHOP_STATE_FILE = "shop_state.db"

# Limites
MAX_IMAGE_BYTES = 700_000
MAX_ITENS = 40

# Cores
COR_PRINCIPAL = 0x5865F2
COR_SUCESSO = 0x57F287
COR_ERRO = 0xED4245
COR_AVISO = 0xFEE75C
COR_INFO = 0x3498DB
COR_DARK = 0x111318
COR_FORTNITE = 0x7B61FF

# Antispam
SPAM_MAX_MENSAGENS = 6
SPAM_JANELA = 8

# Links permitidos no anti-link
LINKS_PERMITIDOS = (
    "discord.com",
    "discord.gg",
    "discordapp.com",
    "youtube.com",
    "youtu.be",
    "github.com",
)


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.reactions = True


# ============================================================
# BOT
# ============================================================

class VoidHelper(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True,
            max_messages=100,
        )

        self.db = None
        self.http_session = None

        # Antispam limitado em memória
        self.spam_cache = defaultdict(lambda: deque(maxlen=10))

        # Controle de cooldown
        self.command_cooldowns = {}

        # Evita iniciar tarefas duas vezes
        self.tasks_started = False

    async def setup_hook(self):

        # Banco
        self.db = sqlite3.connect(
            DATABASE_FILE,
            check_same_thread=False
        )

        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")

        criar_banco(self.db)

        # HTTP
        timeout = aiohttp.ClientTimeout(total=15)

        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(
                limit=4,
                ttl_dns_cache=300
            )
        )

        # Views persistentes
        self.add_view(TicketView())
        self.add_view(RoleView())

        # Sincronizar Slash Commands
        try:
            synced = await self.tree.sync()
            print(f"[VOID] {len(synced)} comandos Slash sincronizados.")
        except Exception as e:
            print(f"[ERRO] Falha ao sincronizar comandos: {e}")

    async def close(self):

        if self.http_session:
            await self.http_session.close()

        if self.db:
            self.db.close()

        await super().close()


bot = VoidHelper()


# ============================================================
# BANCO DE DADOS
# ============================================================

def criar_banco(db):

    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel INTEGER,
            welcome_enabled INTEGER DEFAULT 0,
            autorole_id INTEGER,
            log_channel INTEGER,
            anti_link INTEGER DEFAULT 0,
            anti_spam INTEGER DEFAULT 0,
            ticket_category INTEGER,
            ticket_enabled INTEGER DEFAULT 0,
            welcome_message TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            created_at INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id INTEGER NOT NULL,
            message_id INTEGER PRIMARY KEY,
            role_id INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER PRIMARY KEY
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            shop_hash TEXT,
            message_id INTEGER,
            updated_at INTEGER
        )
    """)

    db.commit()


def garantir_config(guild_id):

    cursor = bot.db.cursor()

    cursor.execute(
        "SELECT guild_id FROM guild_config WHERE guild_id = ?",
        (guild_id,)
    )

    if cursor.fetchone() is None:

        cursor.execute("""
            INSERT INTO guild_config (guild_id)
            VALUES (?)
        """, (guild_id,))

        bot.db.commit()


def obter_config(guild_id):

    garantir_config(guild_id)

    cursor = bot.db.cursor()

    cursor.execute("""
        SELECT
            welcome_channel,
            welcome_enabled,
            autorole_id,
            log_channel,
            anti_link,
            anti_spam,
            ticket_category,
            ticket_enabled,
            welcome_message
        FROM guild_config
        WHERE guild_id = ?
    """, (guild_id,))

    row = cursor.fetchone()

    return {
        "welcome_channel": row[0],
        "welcome_enabled": bool(row[1]),
        "autorole_id": row[2],
        "log_channel": row[3],
        "anti_link": bool(row[4]),
        "anti_spam": bool(row[5]),
        "ticket_category": row[6],
        "ticket_enabled": bool(row[7]),
        "welcome_message": row[8],
    }


def atualizar_config(guild_id, campo, valor):

    garantir_config(guild_id)

    campos_permitidos = {
        "welcome_channel",
        "welcome_enabled",
        "autorole_id",
        "log_channel",
        "anti_link",
        "anti_spam",
        "ticket_category",
        "ticket_enabled",
        "welcome_message",
    }

    if campo not in campos_permitidos:
        return

    cursor = bot.db.cursor()

    cursor.execute(
        f"""
        UPDATE guild_config
        SET {campo} = ?
        WHERE guild_id = ?
        """,
        (valor, guild_id)
    )

    bot.db.commit()


# ============================================================
# EMBEDS
# ============================================================

def embed_sucesso(titulo, descricao):

    return discord.Embed(
        title=f"✅ {titulo}",
        description=descricao,
        color=COR_SUCESSO
    )


def embed_erro(titulo, descricao):

    return discord.Embed(
        title=f"❌ {titulo}",
        description=descricao,
        color=COR_ERRO
    )


def embed_info(titulo, descricao):

    return discord.Embed(
        title=f"💠 {titulo}",
        description=descricao,
        color=COR_PRINCIPAL
    )


def embed_aviso(titulo, descricao):

    return discord.Embed(
        title=f"⚠️ {titulo}",
        description=descricao,
        color=COR_AVISO
    )


# ============================================================
# PERMISSÕES
# ============================================================

def tem_permissao(interaction, permissao):

    if not interaction.guild:
        return False

    return getattr(
        interaction.user.guild_permissions,
        permissao,
        False
    )


def bot_pode_gerenciar_role(guild, role):

    me = guild.me

    if not me:
        return False

    return (
        role < me.top_role
        and not role.is_default()
    )


# ============================================================
# LOGS
# ============================================================

async def enviar_log(guild, titulo, descricao, cor=COR_INFO):

    config = obter_config(guild.id)

    canal_id = config["log_channel"]

    if not canal_id:
        return

    canal = guild.get_channel(canal_id)

    if not canal:
        return

    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor,
        timestamp=datetime.now(timezone.utc)
    )

    try:
        await canal.send(embed=embed)
    except Exception:
        pass


# ============================================================
# WELCOME
# ============================================================

@bot.event
async def on_member_join(member):

    config = obter_config(member.guild.id)

    # Autorole
    role_id = config["autorole_id"]

    if role_id:

        role = member.guild.get_role(role_id)

        if role and bot_pode_gerenciar_role(member.guild, role):

            try:
                await member.add_roles(
                    role,
                    reason="VoidHelper - AutoRole"
                )
            except Exception:
                pass

    # Boas-vindas
    if config["welcome_enabled"]:

        channel_id = config["welcome_channel"]

        if channel_id:

            channel = member.guild.get_channel(channel_id)

            if channel:

                mensagem = config["welcome_message"]

                if not mensagem:
                    mensagem = (
                        "Seja muito bem-vindo(a) **{user}** "
                       "ao servidor **{server}**!"
                    )

                mensagem = mensagem.replace(
                    "{user}",
                    member.mention
                )

                mensagem = mensagem.replace(
                    "{server}",
                    member.guild.name
                )

                embed = discord.Embed(
                    title="👋 Seja bem-vindo!",
                    description=mensagem,
                    color=COR_PRINCIPAL
                )

                embed.set_thumbnail(
                    url=member.display_avatar.url
                )

                embed.set_footer(
                    text=f"Membro #{member.guild.member_count}"
                )

                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass


@bot.event
async def on_member_remove(member):

    config = obter_config(member.guild.id)

    if not config["welcome_enabled"]:
        return

    channel_id = config["welcome_channel"]

    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)

    if not channel:
        return

    embed = discord.Embed(
        title="👋 Até mais!",
        description=(
            f"**{member}** saiu do servidor."
        ),
        color=COR_ERRO
    )

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# ============================================================
# ANTISPAM / ANTI-LINK
# ============================================================

URL_REGEX = re.compile(
    r"(https?://|www\.|discord\.gg/|discord\.com/invite/)",
    re.IGNORECASE
)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if not message.guild:
        await bot.process_commands(message)
        return

    config = obter_config(message.guild.id)

    # ----------------------------------------
    # REAÇÕES AUTOMÁTICAS
    # ----------------------------------------

    if message.channel.id == CANAL_REACOES_ID:

        try:
            await message.add_reaction("🟢")
            await message.add_reaction("⚖️")
            await message.add_reaction("🔴")
        except Exception:
            pass

    # ----------------------------------------
    # ANTI-LINK
    # ----------------------------------------

    if config["anti_link"]:

        conteudo = message.content.lower()

        if URL_REGEX.search(conteudo):

            permitido = any(
                dominio in conteudo
                for dominio in LINKS_PERMITIDOS
            )

            if not permitido:

                if message.author.guild_permissions.manage_messages:
                    pass
                else:

                    try:
                        await message.delete()
                    except Exception:
                        pass

                    try:
                        aviso = await message.channel.send(
                            f"{message.author.mention} "
                            "links não são permitidos aqui.",
                            delete_after=5
                        )
                    except Exception:
                        pass

                    await enviar_log(
                        message.guild,
                        "🔗 Link bloqueado",
                        f"{message.author.mention} enviou um link bloqueado.",
                        COR_AVISO
                    )

                    return

    # ----------------------------------------
    # ANTI-SPAM
    # ----------------------------------------

    if config["anti_spam"]:

        agora = time.monotonic()

        chave = (
            message.guild.id,
            message.author.id
        )

        historico = bot.spam_cache[chave]

        historico.append(agora)

        while historico and agora - historico[0] > SPAM_JANELA:
            historico.popleft()

        if len(historico) >= SPAM_MAX_MENSAGENS:

            if not message.author.guild_permissions.manage_messages:

                try:
                    await message.delete()
                except Exception:
                    pass

                try:
                    await message.author.timeout(
                        discord.utils.utcnow()
                        + discord.timedelta(seconds=30),
                        reason="VoidHelper - Anti-Spam"
                    )
                except Exception:
                    # Compatibilidade com versões onde discord.timedelta
                    # não existe
                    try:
                        from datetime import timedelta

                        await message.author.timeout(
                            timedelta(seconds=30),
                            reason="VoidHelper - Anti-Spam"
                        )
                    except Exception:
                        pass

                historico.clear()

                await enviar_log(
                    message.guild,
                    "🛡️ Anti-Spam",
                    f"{message.author.mention} foi detectado pelo anti-spam.",
                    COR_AVISO
                )

                return

    await bot.process_commands(message)


# ============================================================
# COMANDO: AJUDA
# ============================================================

@bot.tree.command(
    name="ajuda",
    description="Mostra todos os comandos do VoidHelper."
)
async def ajuda(interaction: discord.Interaction):

    embed = discord.Embed(
        title="💠 VoidHelper",
        description=(
            "Seu assistente completo para gerenciamento "
            "e automação do servidor."
        ),
        color=COR_PRINCIPAL
    )

    embed.add_field(
        name="🛡️ Moderação",
        value=(
            "`/kick`\n"
            "`/ban`\n"
            "`/timeout`\n"
            "`/warn`\n"
            "`/warnings`"
        ),
        inline=True
    )

    embed.add_field(
        name="⚙️ Servidor",
        value=(
            "`/config`\n"
            "`/setup`\n"
            "`/serverinfo`\n"
            "`/userinfo`\n"
            "`/avatar`"
        ),
        inline=True
    )

    embed.add_field(
        name="🎫 Sistema",
        value=(
            "`/ticket`\n"
            "`/painel-ticket`\n"
            "`/cargo`"
        ),
        inline=True
    )

    embed.add_field(
        name="🛒 Fortnite",
        value=(
            "`/loja`\n"
            "`/testeloja`"
        ),
        inline=True
    )

    embed.add_field(
        name="🔧 Segurança",
        value=(
            "`/antilink`\n"
            "`/antispam`\n"
            "`/autorole`\n"
            "`/logs`\n"
            "`/boasvindas`"
        ),
        inline=True
    )

    embed.set_footer(
        text="VoidHelper • Administração inteligente"
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# SERVER INFO
# ============================================================

@bot.tree.command(
    name="serverinfo",
    description="Mostra informações do servidor."
)
async def serverinfo(interaction):

    guild = interaction.guild

    if not guild:
        return await interaction.response.send_message(
            "Este comando só pode ser usado em um servidor.",
            ephemeral=True
        )

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        color=COR_PRINCIPAL
    )

    embed.set_thumbnail(
        url=guild.icon.url if guild.icon else discord.Embed.Empty
    )

    embed.add_field(
        name="👥 Membros",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 Canais",
        value=str(len(guild.channels)),
        inline=True
    )

    embed.add_field(
        name="🎭 Cargos",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="🆔 ID",
        value=str(guild.id),
        inline=False
    )

    if guild.owner:
        embed.add_field(
            name="👑 Dono",
            value=guild.owner.mention,
            inline=True
        )

    await interaction.response.send_message(embed=embed)


# ============================================================
# USER INFO
# ============================================================

@bot.tree.command(
    name="userinfo",
    description="Mostra informações de um usuário."
)
@app_commands.describe(
    usuario="Usuário que deseja consultar"
)
async def userinfo(
    interaction,
    usuario: discord.Member = None
):

    usuario = usuario or interaction.user

    embed = discord.Embed(
        title=f"👤 {usuario}",
        color=usuario.color
    )

    embed.set_thumbnail(
        url=usuario.display_avatar.url
    )

    embed.add_field(
        name="🆔 ID",
        value=str(usuario.id),
        inline=False
    )

    embed.add_field(
        name="📅 Conta criada",
        value=discord.utils.format_dt(
            usuario.created_at,
            style="F"
        ),
        inline=False
    )

    if usuario.joined_at:

        embed.add_field(
            name="📥 Entrou no servidor",
            value=discord.utils.format_dt(
                usuario.joined_at,
                style="F"
            ),
            inline=False
        )

    embed.add_field(
        name="🎭 Cargo",
        value=usuario.top_role.mention,
        inline=True
    )

    await interaction.response.send_message(embed=embed)


# ============================================================
# AVATAR
# ============================================================

@bot.tree.command(
    name="avatar",
    description="Mostra o avatar de um usuário."
)
@app_commands.describe(
    usuario="Usuário"
)
async def avatar(
    interaction,
    usuario: discord.Member = None
):

    usuario = usuario or interaction.user

    embed = discord.Embed(
        title=f"🖼️ Avatar de {usuario}",
        color=COR_PRINCIPAL
    )

    embed.set_image(
        url=usuario.display_avatar.url
    )

    await interaction.response.send_message(embed=embed)


# ============================================================
# KICK
# ============================================================

@bot.tree.command(
    name="kick",
    description="Expulsa um membro."
)
@app_commands.describe(
    usuario="Usuário que será expulso",
    motivo="Motivo da expulsão"
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction,
    usuario: discord.Member,
    motivo: str = "Não informado"
):

    if usuario == interaction.user:
        return await interaction.response.send_message(
            "❌ Você não pode expulsar a si mesmo.",
            ephemeral=True
        )

    if usuario.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Esse usuário possui um cargo igual ou superior ao seu.",
            ephemeral=True
        )

    if usuario.top_role >= interaction.guild.me.top_role:
        return await interaction.response.send_message(
            "❌ Meu cargo precisa estar acima do usuário.",
            ephemeral=True
        )

    try:

        await usuario.kick(reason=motivo)

        await interaction.response.send_message(
            embed=embed_sucesso(
                "Usuário expulso",
                f"{usuario.mention} foi expulso.\n\n"
                f"**Motivo:** {motivo}"
            )
        )

        await enviar_log(
            interaction.guild,
            "👢 Membro expulso",
            f"{usuario} foi expulso por {interaction.user.mention}.\n"
            f"**Motivo:** {motivo}",
            COR_AVISO
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Não consegui expulsar o usuário.\n`{e}`",
            ephemeral=True
        )


# ============================================================
# BAN
# ============================================================

@bot.tree.command(
    name="ban",
    description="Bane um membro."
)
@app_commands.describe(
    usuario="Usuário que será banido",
    motivo="Motivo do banimento"
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction,
    usuario: discord.Member,
    motivo: str = "Não informado"
):

    if usuario == interaction.user:
        return await interaction.response.send_message(
            "❌ Você não pode banir a si mesmo.",
            ephemeral=True
        )

    if usuario.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Esse usuário possui um cargo igual ou superior ao seu.",
            ephemeral=True
        )

    if usuario.top_role >= interaction.guild.me.top_role:
        return await interaction.response.send_message(
            "❌ Meu cargo precisa estar acima do usuário.",
            ephemeral=True
        )

    try:

        await usuario.ban(
            reason=motivo,
            delete_message_days=0
        )

        await interaction.response.send_message(
            embed=embed_sucesso(
                "Usuário banido",
                f"{usuario} foi banido.\n\n"
                f"**Motivo:** {motivo}"
            )
        )

        await enviar_log(
            interaction.guild,
            "🔨 Membro banido",
            f"{usuario} foi banido por {interaction.user.mention}.\n"
            f"**Motivo:** {motivo}",
            COR_ERRO
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Não consegui banir o usuário.\n`{e}`",
            ephemeral=True
        )


# ============================================================
# TIMEOUT
# ============================================================

@bot.tree.command(
    name="timeout",
    description="Coloca um membro em timeout."
)
@app_commands.describe(
    usuario="Usuário",
    minutos="Duração em minutos",
    motivo="Motivo"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction,
    usuario: discord.Member,
    minutos: app_commands.Range[int, 1, 40320],
    motivo: str = "Não informado"
):

    if usuario.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Você não pode aplicar timeout nesse usuário.",
            ephemeral=True
        )

    try:

        from datetime import timedelta

        await usuario.timeout(
            timedelta(minutes=minutos),
            reason=motivo
        )

        await interaction.response.send_message(
            embed=embed_sucesso(
                "Timeout aplicado",
                f"{usuario.mention} recebeu timeout por "
                f"**{minutos} minutos**.\n\n"
                f"**Motivo:** {motivo}"
            )
        )

        await enviar_log(
            interaction.guild,
            "🔇 Timeout",
            f"{usuario.mention} recebeu timeout de "
            f"{minutos} minutos.\n"
            f"Moderador: {interaction.user.mention}\n"
            f"Motivo: {motivo}",
            COR_AVISO
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Não consegui aplicar timeout.\n`{e}`",
            ephemeral=True
        )


# ============================================================
# WARN
# ============================================================

@bot.tree.command(
    name="warn",
    description="Adverte um membro."
)
@app_commands.describe(
    usuario="Usuário",
    motivo="Motivo da advertência"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(
    interaction,
    usuario: discord.Member,
    motivo: str = "Não informado"
):

    cursor = bot.db.cursor()

    cursor.execute("""
        INSERT INTO warnings
        (guild_id, user_id, moderator_id, reason, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        interaction.guild.id,
        usuario.id,
        interaction.user.id,
        motivo,
        int(time.time())
    ))

    bot.db.commit()

    cursor.execute("""
        SELECT COUNT(*)
        FROM warnings
        WHERE guild_id = ?
        AND user_id = ?
    """, (
        interaction.guild.id,
        usuario.id
    ))

    total = cursor.fetchone()[0]

    await interaction.response.send_message(
        embed=embed_aviso(
            "Advertência aplicada",
            f"{usuario.mention} recebeu uma advertência.\n\n"
            f"**Motivo:** {motivo}\n"
            f"**Total de advertências:** `{total}`"
        )
    )

    await enviar_log(
        interaction.guild,
        "⚠️ Advertência",
        f"{usuario.mention} recebeu uma advertência.\n"
        f"Moderador: {interaction.user.mention}\n"
        f"Motivo: {motivo}\n"
        f"Total: {total}",
        COR_AVISO
    )


# ============================================================
# WARNINGS
# ============================================================

@bot.tree.command(
    name="warnings",
    description="Mostra as advertências de um usuário."
)
@app_commands.describe(
    usuario="Usuário"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def warnings(
    interaction,
    usuario: discord.Member
):

    cursor = bot.db.cursor()

    cursor.execute("""
        SELECT reason, moderator_id, created_at
        FROM warnings
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (
        interaction.guild.id,
        usuario.id
    ))

    rows = cursor.fetchall()

    embed = discord.Embed(
        title=f"⚠️ Advertências — {usuario}",
        color=COR_AVISO
    )

    if not rows:

        embed.description = "Nenhuma advertência encontrada."

    else:

        linhas = []

        for i, row in enumerate(rows, 1):

            reason, moderator_id, created_at = row

            data = f"<t:{created_at}:R>"

            linhas.append(
                f"**{i}.** {reason}\n"
                f"Moderador: <@{moderator_id}> • {data}"
            )

        embed.description = "\n\n".join(linhas)

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# CONFIGURAÇÃO
# ============================================================

@bot.tree.command(
    name="config",
    description="Mostra a configuração do VoidHelper."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def config(interaction):

    cfg = obter_config(interaction.guild.id)

    def canal(cid):
        return f"<#{cid}>" if cid else "Não configurado"

    def cargo(rid):
        return f"<@&{rid}>" if rid else "Não configurado"

    embed = discord.Embed(
        title="⚙️ Configuração do VoidHelper",
        color=COR_PRINCIPAL
    )

    embed.add_field(
        name="👋 Boas-vindas",
        value=(
            f"Status: `{'ON' if cfg['welcome_enabled'] else 'OFF'}`\n"
            f"Canal: {canal(cfg['welcome_channel'])}"
        ),
        inline=True
    )

    embed.add_field(
        name="🎭 AutoRole",
        value=cargo(cfg["autorole_id"]),
        inline=True
    )

    embed.add_field(
        name="📋 Logs",
        value=canal(cfg["log_channel"]),
        inline=True
    )

    embed.add_field(
        name="🔗 Anti-Link",
        value="🟢 Ativo" if cfg["anti_link"] else "🔴 Desativado",
        inline=True
    )

    embed.add_field(
        name="🛡️ Anti-Spam",
        value="🟢 Ativo" if cfg["anti_spam"] else "🔴 Desativado",
        inline=True
    )

    embed.add_field(
        name="🎫 Tickets",
        value="🟢 Ativo" if cfg["ticket_enabled"] else "🔴 Desativado",
        inline=True
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# SETUP
# ============================================================

@bot.tree.command(
    name="setup",
    description="Configura automaticamente recursos básicos."
)
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction):

    guild = interaction.guild

    garantir_config(guild.id)

    # Categoria
    categoria = discord.utils.get(
        guild.categories,
        name="VOIDHELPER"
    )

    if not categoria:

        try:
            categoria = await guild.create_category(
                "VOIDHELPER",
                reason="VoidHelper Setup"
            )
        except Exception:
            categoria = None

    # Canal de logs
    log_channel = discord.utils.find(
        lambda c: c.name == "void-logs",
        guild.text_channels
    )

    if not log_channel:

        try:
            log_channel = await guild.create_text_channel(
                "void-logs",
                category=categoria,
                reason="VoidHelper Setup"
            )
        except Exception:
            log_channel = None

    # Canal de boas-vindas
    welcome_channel = discord.utils.find(
        lambda c: c.name == "boas-vindas",
        guild.text_channels
    )

    if not welcome_channel:

        try:
            welcome_channel = await guild.create_text_channel(
                "boas-vindas",
                category=categoria,
                reason="VoidHelper Setup"
            )
        except Exception:
            welcome_channel = None

    # Atualização
    if log_channel:
        atualizar_config(
            guild.id,
            "log_channel",
            log_channel.id
        )

    if welcome_channel:
        atualizar_config(
            guild.id,
            "welcome_channel",
            welcome_channel.id
        )

    atualizar_config(
        guild.id,
        "welcome_enabled",
        1
    )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "Setup concluído",
            (
                "A configuração inicial do VoidHelper foi realizada.\n\n"
                f"📋 Logs: {log_channel.mention if log_channel else 'Falhou'}\n"
                f"👋 Boas-vindas: "
                f"{welcome_channel.mention if welcome_channel else 'Falhou'}\n"
                f"🎫 Categoria: "
                f"{categoria.mention if categoria else 'Falhou'}"
            )
        )
    )


# ============================================================
# BOAS-VINDAS
# ============================================================

@bot.tree.command(
    name="boasvindas",
    description="Configura o sistema de boas-vindas."
)
@app_commands.describe(
    canal="Canal de boas-vindas",
    mensagem="Mensagem personalizada"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def boasvindas(
    interaction,
    canal: discord.TextChannel,
    mensagem: str = None
):

    atualizar_config(
        interaction.guild.id,
        "welcome_channel",
        canal.id
    )

    atualizar_config(
        interaction.guild.id,
        "welcome_enabled",
        1
    )

    if mensagem:
        atualizar_config(
            interaction.guild.id,
            "welcome_message",
            mensagem
        )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "Boas-vindas configuradas",
            (
                f"Canal: {canal.mention}\n"
                "Use `{user}` para mencionar o membro.\n"
                "Use `{server}` para o nome do servidor."
            )
        )
    )


# ============================================================
# AUTOROLE
# ============================================================

@bot.tree.command(
    name="autorole",
    description="Define o cargo automático."
)
@app_commands.describe(
    cargo="Cargo que novos membros receberão"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole(
    interaction,
    cargo: discord.Role
):

    if not bot_pode_gerenciar_role(
        interaction.guild,
        cargo
    ):
        return await interaction.response.send_message(
            "❌ Meu cargo precisa estar acima desse cargo.",
            ephemeral=True
        )

    atualizar_config(
        interaction.guild.id,
        "autorole_id",
        cargo.id
    )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "AutoRole configurado",
            f"Novos membros receberão {cargo.mention}."
        )
    )


# ============================================================
# LOGS
# ============================================================

@bot.tree.command(
    name="logs",
    description="Define o canal de logs."
)
@app_commands.describe(
    canal="Canal de logs"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def logs(
    interaction,
    canal: discord.TextChannel
):

    atualizar_config(
        interaction.guild.id,
        "log_channel",
        canal.id
    )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "Logs configurados",
            f"Os logs serão enviados para {canal.mention}."
        )
    )


# ============================================================
# ANTI-LINK
# ============================================================

@bot.tree.command(
    name="antilink",
    description="Ativa ou desativa o anti-link."
)
@app_commands.describe(
    ativo="Ativar ou desativar"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def antilink(
    interaction,
    ativo: bool
):

    atualizar_config(
        interaction.guild.id,
        "anti_link",
        int(ativo)
    )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "Anti-Link atualizado",
            f"Status: **{'ATIVO' if ativo else 'DESATIVADO'}**"
        )
    )


# ============================================================
# ANTI-SPAM
# ============================================================

@bot.tree.command(
    name="antispam",
    description="Ativa ou desativa o anti-spam."
)
@app_commands.describe(
    ativo="Ativar ou desativar"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def antispam(
    interaction,
    ativo: bool
):

    atualizar_config(
        interaction.guild.id,
        "anti_spam",
        int(ativo)
    )

    await interaction.response.send_message(
        embed=embed_sucesso(
            "Anti-Spam atualizado",
            f"Status: **{'ATIVO' if ativo else 'DESATIVADO'}**"
        )
    )


# ============================================================
# TICKETS
# ============================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="voidhelper_ticket"
    )
    async def abrir_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        if not guild:
            return

        cursor = bot.db.cursor()

        cursor.execute("""
            SELECT channel_id
            FROM tickets
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            guild.id,
            interaction.user.id
        ))

        existente = cursor.fetchone()

        if existente:

            canal_existente = guild.get_channel(
                existente[0]
            )

            if canal_existente:

                return await interaction.response.send_message(
                    f"❌ Você já possui um ticket: "
                    f"{canal_existente.mention}",
                    ephemeral=True
                )

            cursor.execute(
                """
                DELETE FROM tickets
                WHERE channel_id = ?
                """,
                (existente[0],)
            )

            bot.db.commit()

        config = obter_config(guild.id)

        categoria = None

        if config["ticket_category"]:

            categoria = guild.get_channel(
                config["ticket_category"]
            )

        if not categoria:

            categoria = discord.utils.get(
                guild.categories,
                name="TICKETS"
            )

        if not categoria:

            try:

                categoria = await guild.create_category(
                    "TICKETS"
                )

                atualizar_config(
                    guild.id,
                    "ticket_category",
                    categoria.id
                )

            except Exception:

                categoria = None

        nome = (
            f"ticket-{interaction.user.name}"
            .lower()
            .replace(" ", "-")
        )

        nome = re.sub(
            r"[^a-z0-9\-]",
            "",
            nome
        )[:90]

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                ),

            guild.me:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    read_message_history=True
                )
        }

        try:

            canal = await guild.create_text_channel(
                nome,
                category=categoria,
                overwrites=overwrites,
                reason="VoidHelper - Ticket"
            )

        except Exception as e:

            return await interaction.response.send_message(
                f"❌ Não consegui criar o ticket.\n`{e}`",
                ephemeral=True
            )

        cursor.execute("""
            INSERT OR REPLACE INTO tickets
            (guild_id, user_id, channel_id)
            VALUES (?, ?, ?)
        """, (
            guild.id,
            interaction.user.id,
            canal.id
        ))

        bot.db.commit()

        embed = discord.Embed(
            title="🎫 Ticket aberto",
            description=(
                f"Olá {interaction.user.mention}!\n\n"
                "Explique sua solicitação abaixo.\n"
                "Nossa equipe responderá assim que possível."
            ),
            color=COR_PRINCIPAL
        )

        await canal.send(
            embed=embed,
            view=CloseTicketView()
        )

        await interaction.response.send_message(
            f"🎫 Ticket criado: {canal.mention}",
            ephemeral=True
        )


class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="voidhelper_close_ticket"
    )
    async def fechar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.administrator
        ):

            cursor = bot.db.cursor()

            cursor.execute("""
                SELECT user_id
                FROM tickets
                WHERE channel_id = ?
            """, (
                interaction.channel.id,
            ))

            row = cursor.fetchone()

            if not row or row[0] != interaction.user.id:

                return await interaction.response.send_message(
                    "❌ Você não pode fechar este ticket.",
                    ephemeral=True
                )

        cursor = bot.db.cursor()

        cursor.execute(
            """
            DELETE FROM tickets
            WHERE channel_id = ?
            """,
            (interaction.channel.id,)
        )

        bot.db.commit()

        await interaction.response.send_message(
            "🔒 Ticket sendo fechado..."
        )

        await asyncio.sleep(2)

        try:
            await interaction.channel.delete(
                reason="VoidHelper - Ticket fechado"
            )
        except Exception:
            pass


class TicketPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="voidhelper_ticket_panel"
    )
    async def ticket(
        self,
        interaction,
        button
    ):

        view = TicketView()

        # Executa a mesma lógica através da view principal
        await interaction.response.send_message(
            "Clique abaixo para criar seu ticket:",
            view=view,
            ephemeral=True
        )


@bot.tree.command(
    name="painel-ticket",
    description="Envia o painel de tickets."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def painel_ticket(interaction):

    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description=(
            "Precisa de ajuda?\n\n"
            "Clique no botão abaixo para abrir um ticket "
            "privado com a equipe."
        ),
        color=COR_PRINCIPAL
    )

    embed.set_footer(
        text="VoidHelper • Atendimento"
    )

    await interaction.channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "✅ Painel enviado.",
        ephemeral=True
    )


@bot.tree.command(
    name="ticket",
    description="Abre um ticket."
)
async def ticket(interaction):

    view = TicketView()

    await interaction.response.send_message(
        "Clique no botão abaixo:",
        view=view,
        ephemeral=True
    )


# ============================================================
# CARGOS POR BOTÃO
# ============================================================

class RoleView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Receber cargo",
        emoji="🎭",
        style=discord.ButtonStyle.primary,
        custom_id="voidhelper_role"
    )
    async def role_button(
        self,
        interaction,
        button
    ):

        cursor = bot.db.cursor()

        cursor.execute("""
            SELECT role_id
            FROM reaction_roles
            WHERE message_id = ?
        """, (
            interaction.message.id,
        ))

        row = cursor.fetchone()

        if not row:

            return await interaction.response.send_message(
                "❌ Este painel não está configurado.",
                ephemeral=True
            )

        role = interaction.guild.get_role(row[0])

        if not role:

            return await interaction.response.send_message(
                "❌ O cargo não existe mais.",
                ephemeral=True
            )

        if not bot_pode_gerenciar_role(
            interaction.guild,
            role
        ):

            return await interaction.response.send_message(
                "❌ Não consigo gerenciar este cargo.",
                ephemeral=True
            )

        try:

            if role in interaction.user.roles:

                await interaction.user.remove_roles(role)

                texto = f"Cargo {role.mention} removido."

            else:

                await interaction.user.add_roles(role)

                texto = f"Cargo {role.mention} adicionado."

            await interaction.response.send_message(
                f"✅ {texto}",
                ephemeral=True
            )

        except Exception as e:

            await interaction.response.send_message(
                f"❌ Erro: `{e}`",
                ephemeral=True
            )


@bot.tree.command(
    name="cargo",
    description="Cria um painel para receber um cargo."
)
@app_commands.describe(
    cargo="Cargo que será entregue"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def cargo(
    interaction,
    cargo: discord.Role
):

    if not bot_pode_gerenciar_role(
        interaction.guild,
        cargo
    ):

        return await interaction.response.send_message(
            "❌ Meu cargo precisa estar acima do cargo escolhido.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🎭 Escolha de cargo",
        description=(
            f"Clique no botão abaixo para receber/remover "
            f"o cargo {cargo.mention}."
        ),
        color=COR_PRINCIPAL
    )

    mensagem = await interaction.channel.send(
        embed=embed,
        view=RoleView()
    )

    cursor = bot.db.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO reaction_roles
        (guild_id, message_id, role_id)
        VALUES (?, ?, ?)
    """, (
        interaction.guild.id,
        mensagem.id,
        cargo.id
    ))

    bot.db.commit()

    await interaction.response.send_message(
        "✅ Painel de cargo criado.",
        ephemeral=True
    )


# ============================================================
# FORTNITE SHOP
# ============================================================

RARIDADE_CORES = {
    "common": 0xB7B7B7,
    "uncommon": 0x57F287,
    "rare": 0x3498DB,
    "epic": 0x9B59B6,
    "legendary": 0xF1C40F,
    "mythic": 0xF4B942,
    "marvel": 0xE74C3C,
    "dc": 0x3498DB,
    "icon": 0xFF66CC,
    "dark": 0x555555,
    "slurp": 0x4CC9F0,
    "gaminglegends": 0xE91E63,
}


def nome_raridade(rarity):

    nomes = {
        "common": "Comum",
        "uncommon": "Incomum",
        "rare": "Raro",
        "epic": "Épico",
        "legendary": "Lendário",
        "mythic": "Mítico",
        "marvel": "Marvel",
        "dc": "DC",
        "icon": "Ícone",
        "dark": "Sombrio",
        "slurp": "Slurp",
        "gaminglegends": "Gaming Legends",
    }

    return nomes.get(
        str(rarity or "").lower(),
        "Especial"
    )


def cor_raridade(rarity):

    return RARIDADE_CORES.get(
        str(rarity or "").lower(),
        COR_PRINCIPAL
    )


async def buscar_loja():

    if not bot.http_session:
        return None

    try:

        async with bot.http_session.get(
            FORTNITE_SHOP_URL,
            params={"language": IDIOMA}
        ) as response:

            if response.status != 200:
                print(
                    f"[LOJA] API retornou HTTP {response.status}"
                )
                return None

            return await response.json()

    except Exception as e:

        print(f"[LOJA] Erro: {e}")
        return None


def extrair_itens(data):

    if not data:
        return []

    items = []

    shop_entries = (
        data.get("data", {})
        .get("entries", [])
    )

    vistos = set()

    for entry in shop_entries:

        if len(items) >= MAX_ITENS:
            break

        br_items = entry.get("brItems") or []

        if not br_items:
            continue

        item = br_items[0]

        item_id = item.get("id")

        if not item_id:
            continue

        if item_id in vistos:
            continue

        vistos.add(item_id)

        name = (
            item.get("name")
            or item.get("description")
            or "Item desconhecido"
        )

        rarity = (
            item.get("rarity", {})
            .get("value")
            if isinstance(item.get("rarity"), dict)
            else item.get("rarity")
        )

        type_data = item.get("type") or {}

        category = (
            type_data.get("displayValue")
            or type_data.get("value")
            or "Item"
        )

        images = item.get("images") or {}

        image = (
            images.get("featured")
            or images.get("icon")
            or images.get("background")
        )

        price = entry.get("finalPrice")

        if price is None:
            price = entry.get("regularPrice")

        if price is None:
            price = 0

        items.append({
            "id": item_id,
            "name": name,
            "rarity": rarity,
            "category": category,
            "image": image,
            "price": price,
        })

    return items


async def baixar_imagem(session, url):

    if not url:
        return None

    try:

        async with session.get(url) as response:

            if response.status != 200:
                return None

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:

                try:

                    if int(content_length) > MAX_IMAGE_BYTES:
                        return None

                except ValueError:
                    pass

            data = await response.read(
                MAX_IMAGE_BYTES + 1
            )

            if len(data) > MAX_IMAGE_BYTES:
                return None

            return data

    except Exception:
        return None


# ============================================================
# HASH DA LOJA
# ============================================================

def gerar_hash_loja(itens):

    texto = "|".join(
        f"{item['id']}:{item['price']}"
        for item in itens
    )

    return hashlib.sha256(
        texto.encode()
    ).hexdigest()


def obter_shop_state():

    cursor = bot.db.cursor()

    cursor.execute("""
        SELECT shop_hash, message_id, updated_at
        FROM shop_state
        WHERE id = 1
    """)

    row = cursor.fetchone()

    if not row:
        return None, None, None

    return row


def salvar_shop_state(
    shop_hash,
    message_id,
    updated_at
):

    bot.db.execute("""
        INSERT OR REPLACE INTO shop_state
        (id, shop_hash, message_id, updated_at)
        VALUES (1, ?, ?, ?)
    """, (
        shop_hash,
        message_id,
        updated_at
    ))

    bot.db.commit()


# ============================================================
# GERADOR DA IMAGEM DA LOJA
# ============================================================

async def gerar_imagem_loja(itens):

    try:

        from PIL import Image, ImageDraw, ImageFont

    except ImportError:

        return None

    largura = 1200
    card_largura = 220
    card_altura = 290

    colunas = 5

    linhas = (
        (len(itens) + colunas - 1)
        // colunas
    )

    altura = 180 + (
        linhas * (card_altura + 20)
    ) + 80

    imagem = Image.new(
        "RGB",
        (largura, altura),
        (12, 14, 20)
    )

    draw = ImageDraw.Draw(imagem)

    # Fundo
    for y in range(altura):

        valor = int(
            14 + (y / max(altura, 1)) * 16
        )

        draw.line(
            [(0, y), (largura, y)],
            fill=(valor, valor, valor + 8)
        )

    # Cabeçalho
    draw.rectangle(
        (0, 0, largura, 145),
        fill=(20, 20, 35)
    )

    fonte_titulo = ImageFont.truetype(
        "DejaVuSans-Bold.ttf",
        46
    )

    fonte_sub = ImageFont.truetype(
        "DejaVuSans.ttf",
        20
    )

    draw.text(
        (40, 28),
        "FORTNITE ITEM SHOP",
        font=fonte_titulo,
        fill=(255, 255, 255)
    )

    draw.text(
        (42, 88),
        "LOJA ATUALIZADA AUTOMATICAMENTE PELO VOIDHELPER",
        font=fonte_sub,
        fill=(170, 170, 190)
    )

    agora = datetime.now()

    draw.text(
        (40, 118),
        agora.strftime("%d/%m/%Y • %H:%M"),
        font=fonte_sub,
        fill=(125, 130, 255)
    )

    # Painel
    session = bot.http_session

    for index, item in enumerate(itens):

        coluna = index % colunas
        linha = index // colunas

        x = 40 + coluna * 235
        y = 165 + linha * (card_altura + 20)

        rarity_color = cor_raridade(
            item["rarity"]
        )

        # Card
        draw.rounded_rectangle(
            (
                x,
                y,
                x + card_largura,
                y + card_altura
            ),
            radius=14,
            fill=(25, 27, 36),
            outline=rarity_color,
            width=3
        )

        # Imagem
        image_data = await baixar_imagem(
            session,
            item["image"]
        )

        if image_data:

            try:

                item_img = Image.open(
                    io.BytesIO(image_data)
                ).convert("RGBA")

                item_img.thumbnail(
                    (190, 180)
                )

                px = (
                    x
                    + (card_largura - item_img.width)
                    // 2
                )

                py = y + 12

                imagem.paste(
                    item_img,
                    (px, py),
                    item_img
                )

            except Exception:
                pass

        # Raridade
        draw.rounded_rectangle(
            (
                x + 10,
                y + 194,
                x + card_largura - 10,
                y + 222
            ),
            radius=7,
            fill=rarity_color
        )

        fonte_raridade = ImageFont.truetype(
            "DejaVuSans-Bold.ttf",
            13
        )

        draw.text(
            (x + 20, y + 200),
            nome_raridade(item["rarity"]),
            font=fonte_raridade,
            fill=(255, 255, 255)
        )

        fonte_nome = ImageFont.truetype(
            "DejaVuSans-Bold.ttf",
            15
        )

        nome = str(item["name"])

        if len(nome) > 24:
            nome = nome[:21] + "..."

        draw.text(
            (x + 12, y + 230),
            nome,
            font=fonte_nome,
            fill=(255, 255, 255)
        )

        fonte_preco = ImageFont.truetype(
            "DejaVuSans-Bold.ttf",
            15
        )

        draw.text(
            (x + 12, y + 255),
            f"🪙 {item['price']} V-Bucks",
            font=fonte_preco,
            fill=(255, 220, 80)
        )

    # Rodapé
    rodape_y = altura - 55

    draw.text(
        (40, rodape_y),
        f"VoidHelper • {len(itens)} itens encontrados",
        font=fonte_sub,
        fill=(130, 130, 150)
    )

    output = io.BytesIO()

    imagem.save(
        output,
        format="JPEG",
        quality=78,
        optimize=True
    )

    output.seek(0)

    # Liberar memória
    imagem.close()
    del imagem

    gc.collect()

    return output


# ============================================================
# ATUALIZAÇÃO DA LOJA
# ============================================================

async def atualizar_loja(forcar=False):

    data = await buscar_loja()

    if not data:
        return False

    itens = extrair_itens(data)

    if not itens:
        print("[LOJA] Nenhum item encontrado.")
        return False

    shop_hash = gerar_hash_loja(itens)

    old_hash, old_message_id, old_updated = obter_shop_state()

    if (
        not forcar
        and old_hash
        and old_hash == shop_hash
    ):
        return False

    canal = bot.get_channel(CANAL_LOJA_ID)

    if not canal:

        try:
            canal = await bot.fetch_channel(
                CANAL_LOJA_ID
            )
        except Exception:
            return False

    imagem = await gerar_imagem_loja(itens)

    if not imagem:
        return False

    arquivo = discord.File(
        imagem,
        filename="voidhelper_loja.jpg"
    )

    embed = discord.Embed(
        title="🛒 Loja Fortnite",
        description=(
            "A loja foi atualizada!\n\n"
            "Confira os itens disponíveis abaixo."
        ),
        color=COR_FORTNITE,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="📦 Itens",
        value=str(len(itens)),
        inline=True
    )

    embed.add_field(
        name="🕐 Atualização",
        value=discord.utils.format_dt(
            datetime.now(timezone.utc),
            style="R"
        ),
        inline=True
    )

    embed.set_image(
        url="attachment://voidhelper_loja.jpg"
    )

    embed.set_footer(
        text="VoidHelper • Fortnite Item Shop"
    )

    mensagem = None

    if old_message_id:

        try:
            mensagem = await canal.fetch_message(
                old_message_id
            )
        except Exception:
            mensagem = None

    try:

        if mensagem:

            await mensagem.edit(
                content=None,
                embed=embed,
                attachments=[arquivo]
            )

        else:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo
            )

        salvar_shop_state(
            shop_hash,
            mensagem.id,
            int(time.time())
        )

        print(
            f"[LOJA] Atualizada. {len(itens)} itens."
        )

        return True

    except Exception as e:

        print(
            f"[LOJA] Erro ao enviar loja: {e}"
        )

        return False

    finally:

        try:
            imagem.close()
        except Exception:
            pass

        gc.collect()


# ============================================================
# COMANDO LOJA
# ============================================================

@bot.tree.command(
    name="loja",
    description="Mostra a situação da loja Fortnite."
)
async def loja(interaction):

    await interaction.response.defer(
        ephemeral=True
    )

    data = await buscar_loja()

    if not data:

        return await interaction.followup.send(
            "❌ Não foi possível consultar a loja."
        )

    itens = extrair_itens(data)

    if not itens:

        return await interaction.followup.send(
            "❌ Nenhum item encontrado."
        )

    embed = discord.Embed(
        title="🛒 Loja Fortnite",
        description=(
            f"A loja possui **{len(itens)} itens** "
            "registrados atualmente.\n\n"
            f"Confira a loja completa em <#{CANAL_LOJA_ID}>."
        ),
        color=COR_FORTNITE
    )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# TESTE DA LOJA
# ============================================================

@bot.tree.command(
    name="testeloja",
    description="Força uma atualização da loja Fortnite."
)
@app_commands.checks.has_permissions(administrator=True)
async def testeloja(interaction):

    await interaction.response.defer(
        ephemeral=True
    )

    sucesso = await atualizar_loja(
        forcar=True
    )

    if sucesso:

        await interaction.followup.send(
            "✅ Loja Fortnite atualizada com sucesso."
        )

    else:

        await interaction.followup.send(
            "❌ Não foi possível atualizar a loja."
        )


# ============================================================
# COMANDO PREFIXO ANTIGO
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(administrator=True)
async def testeloja_prefix(ctx):

    mensagem = await ctx.send(
        "⏳ Atualizando a loja..."
    )

    sucesso = await atualizar_loja(
        forcar=True
    )

    if sucesso:

        await mensagem.edit(
            content="✅ Loja atualizada."
        )

    else:

        await mensagem.edit(
            content="❌ Não foi possível atualizar a loja."
        )


# ============================================================
# TASK DA LOJA
# ============================================================

@tasks.loop(seconds=INTERVALO_VERIFICACAO)
async def verificar_loja():

    try:

        await atualizar_loja()

    except Exception as e:

        print(
            f"[LOJA] Erro na verificação automática: {e}"
        )

    # Limpeza de memória
    if len(bot.spam_cache) > 2000:

        bot.spam_cache.clear()

    gc.collect()


@verificar_loja.before_loop
async def antes_loja():

    await bot.wait_until_ready()


# ============================================================
# ERROS DOS SLASH COMMANDS
# ============================================================

@bot.tree.error
async def on_app_command_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        mensagem = (
            "❌ Você não possui permissão "
            "para utilizar este comando."
        )

    elif isinstance(
        error,
        app_commands.errors.CommandOnCooldown
    ):

        mensagem = (
            f"⏳ Aguarde {error.retry_after:.1f}s."
        )

    else:

        print(
            f"[COMANDO] Erro: {error}"
        )

        mensagem = (
            "❌ Ocorreu um erro ao executar o comando."
        )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                mensagem,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                mensagem,
                ephemeral=True
            )

    except Exception:
        pass


# ============================================================
# ERROS DOS COMANDOS PREFIXADOS
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ Você não possui permissão para isso.",
            delete_after=5
        )

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    print(
        f"[PREFIXO] Erro: {error}"
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print("=" * 50)
    print("VOIDHELPER ONLINE")
    print("=" * 50)

    print(f"Bot: {bot.user}")
    print(f"ID: {bot.user.id}")
    print(f"Servidores: {len(bot.guilds)}")
    print(f"RAM: modo otimizado")
    print("=" * 50)

    if not verificar_loja.is_running():

        verificar_loja.start()


# ============================================================
# ENCERRAMENTO
# ============================================================

async def main():

    if not TOKEN:

        print(
            "ERRO: DISCORD_TOKEN não configurado."
        )

        return

    try:

        await bot.start(TOKEN)

    except KeyboardInterrupt:

        pass

    finally:

        if not bot.is_closed():

            await bot.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "\nVoidHelper encerrado."
        )