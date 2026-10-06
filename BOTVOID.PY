import discord
from discord.ext import commands

# ==========================================
# CONFIGURAÇÕES
# ==========================================

import os

TOKEN = os.getenv("DISCORD_TOKEN")

# Coloque aqui o ID do canal onde o bot deve reagir
CANAL_ID = 1556998399461691443


# ==========================================
# CONFIGURAÇÃO DO BOT
# ==========================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ==========================================
# QUANDO O BOT INICIAR
# ==========================================

@bot.event
async def on_ready():
    print("=" * 40)
    print(f"Bot conectado como: {bot.user}")
    print(f"ID do bot: {bot.user.id}")
    print(f"Canal configurado: {CANAL_ID}")
    print("=" * 40)


# ==========================================
# QUANDO ALGUÉM ENVIAR UMA MENSAGEM
# ==========================================

@bot.event
async def on_message(message):

    # Ignora mensagens enviadas por bots
    if message.author.bot:
        return

    # Verifica se a mensagem foi enviada no canal correto
    if message.channel.id == CANAL_ID:

        try:
            # W
            await message.add_reaction("🟢")

            # Balança
            await message.add_reaction("⚖️")

            # L
            await message.add_reaction("🔴")

            print(
                f"Reações adicionadas na mensagem de "
                f"{message.author}."
            )

        except discord.Forbidden:
            print(
                "ERRO: O bot não possui permissão "
                "para adicionar reações."
            )

        except discord.HTTPException as erro:
            print(f"Erro do Discord: {erro}")

    # Mantém os comandos funcionando
    await bot.process_commands(message)


# ==========================================
# INICIAR BOT
# ==========================================

bot.run(TOKEN)