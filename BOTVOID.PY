import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import os
import json

from datetime import datetime, timezone


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")


# ============================================================
# CANAL DAS REAÇÕES
# ============================================================

CANAL_REACOES_ID = 1556998399461691443


# ============================================================
# CANAL DA LOJA DO FORTNITE
# ============================================================

CANAL_LOJA_ID = 1214658145243234324


# ============================================================
# API DO FORTNITE
# ============================================================

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

IDIOMA = "pt-BR"


# ============================================================
# ARQUIVO DE ESTADO
# ============================================================

SHOP_STATE_FILE = "shop_state.json"


# ============================================================
# CONFIGURAÇÃO DO BOT
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# VARIÁVEIS DA LOJA
# ============================================================

ultima_loja_publicada = None
mensagem_loja_id = None

loja_atual = []

# Quantos cards por página
CARDS_POR_PAGINA = 4


# ============================================================
# CARREGAR ESTADO
# ============================================================

def carregar_estado():

    global ultima_loja_publicada
    global mensagem_loja_id

    try:

        if not os.path.exists(
            SHOP_STATE_FILE
        ):
            return

        with open(
            SHOP_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            dados = json.load(arquivo)

        ultima_loja_publicada = dados.get(
            "shop_hash"
        )

        mensagem_loja_id = dados.get(
            "message_id"
        )

        print(
            f"Hash salvo: {ultima_loja_publicada}"
        )

        print(
            f"Mensagem salva: {mensagem_loja_id}"
        )

    except Exception as erro:

        print(
            f"Erro ao carregar estado: {erro}"
        )


# ============================================================
# SALVAR ESTADO
# ============================================================

def salvar_estado(
    shop_hash,
    message_id
):

    global ultima_loja_publicada
    global mensagem_loja_id

    ultima_loja_publicada = shop_hash
    mensagem_loja_id = message_id

    try:

        with open(
            SHOP_STATE_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                {
                    "shop_hash": shop_hash,
                    "message_id": message_id
                },
                arquivo,
                indent=4
            )

    except Exception as erro:

        print(
            f"Erro ao salvar estado: {erro}"
        )


# ============================================================
# CONSULTAR API
# ============================================================

async def buscar_loja():

    try:

        timeout = aiohttp.ClientTimeout(
            total=30
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                FORTNITE_SHOP_URL,
                params={
                    "language": IDIOMA
                }
            ) as response:

                if response.status != 200:

                    print(
                        f"API retornou HTTP "
                        f"{response.status}"
                    )

                    return None

                dados = await response.json()

                return dados

    except asyncio.TimeoutError:

        print(
            "Tempo limite da API excedido."
        )

    except aiohttp.ClientError as erro:

        print(
            f"Erro de conexão com API: {erro}"
        )

    except Exception as erro:

        print(
            f"Erro consultando API: {erro}"
        )

    return None


# ============================================================
# OBTER IMAGEM
# ============================================================

def obter_imagem(item):

    images = item.get(
        "images",
        {}
    )

    if not isinstance(
        images,
        dict
    ):
        return None

    # Featured costuma ser a melhor imagem
    for chave in (
        "featured",
        "icon",
        "smallIcon"
    ):

        imagem = images.get(
            chave
        )

        if imagem:
            return imagem

    return None


# ============================================================
# OBTER RARIDADE
# ============================================================

def obter_raridade(item):

    rarity = item.get(
        "rarity"
    )

    if isinstance(
        rarity,
        dict
    ):

        return (
            rarity.get("displayValue")
            or rarity.get("value")
            or "Desconhecida"
        )

    if rarity:

        return str(rarity)

    return "Desconhecida"


# ============================================================
# OBTER TIPO
# ============================================================

def obter_tipo(item):

    tipo = item.get(
        "type"
    )

    if isinstance(
        tipo,
        dict
    ):

        return (
            tipo.get("displayValue")
            or tipo.get("value")
            or "Cosmético"
        )

    if tipo:

        return str(tipo)

    return "Cosmético"


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preco(preco):

    try:

        preco = int(preco)

        return (
            f"{preco:,}"
            .replace(",", ".")
        )

    except Exception:

        return str(preco)


# ============================================================
# EXTRAIR ITENS DE UMA ENTRY
# ============================================================

def obter_itens_entry(entry):

    itens = []

    # Battle Royale
    br_items = entry.get(
        "brItems"
    )

    if isinstance(
        br_items,
        list
    ):

        itens.extend(
            br_items
        )

    # Outros tipos
    for chave in (
        "tracks",
        "instruments",
        "cars",
        "legoKits",
        "items",
        "cosmetics"
    ):

        valor = entry.get(
            chave
        )

        if isinstance(
            valor,
            list
        ):

            itens.extend(
                valor
            )

    # Caso a própria entry seja um item
    if not itens:

        if (
            entry.get("name")
            or entry.get("id")
        ):

            itens.append(
                entry
            )

    return itens


# ============================================================
# EXTRAIR TODA A LOJA
# ============================================================

def extrair_itens(data):

    entries = data.get(
        "entries",
        []
    )

    resultado = []

    if not isinstance(
        entries,
        list
    ):

        return resultado

    ids_adicionados = set()

    for entry in entries:

        if not isinstance(
            entry,
            dict
        ):
            continue

        itens = obter_itens_entry(
            entry
        )

        # Tenta encontrar o preço
        preco = (
            entry.get("finalPrice")
            or entry.get("final_price")
            or entry.get("regularPrice")
            or 0
        )

        for item in itens:

            if not isinstance(
                item,
                dict
            ):
                continue

            nome = item.get(
                "name"
            )

            if not nome:

                continue

            item_id = item.get(
                "id"
            )

            # Evita duplicar o mesmo item
            # quando ele aparece em mais
            # de uma estrutura da API.
            chave = item_id or nome

            if chave in ids_adicionados:

                continue

            ids_adicionados.add(
                chave
            )

            resultado.append(
                {
                    "id": item_id,
                    "name": nome,
                    "description": item.get(
                        "description",
                        ""
                    ),
                    "type": obter_tipo(
                        item
                    ),
                    "rarity": obter_raridade(
                        item
                    ),
                    "image": obter_imagem(
                        item
                    ),
                    "price": preco
                }
            )

    return resultado


# ============================================================
# EMOJI DO TIPO
# ============================================================

def emoji_tipo(tipo):

    tipo_lower = str(
        tipo
    ).lower()

    if (
        "outfit" in tipo_lower
        or "traje" in tipo_lower
        or "skin" in tipo_lower
    ):
        return "👕"

    if (
        "pickaxe" in tipo_lower
        or "picareta" in tipo_lower
    ):
        return "⛏️"

    if (
        "emote" in tipo_lower
        or "emote" in tipo_lower
    ):
        return "🎵"

    if (
        "glider" in tipo_lower
        or "asa" in tipo_lower
    ):
        return "🪂"

    if "wrap" in tipo_lower:

        return "🎨"

    if "back" in tipo_lower:

        return "🎒"

    if "contrail" in tipo_lower:

        return "💨"

    if "loading" in tipo_lower:

        return "🖼️"

    return "🎮"


# ============================================================
# CRIAR CARD
# ============================================================

def criar_card(item):

    embed = discord.Embed(
        color=discord.Color.from_rgb(
            88,
            101,
            242
        )
    )

    tipo = item.get(
        "type",
        "Cosmético"
    )

    emoji = emoji_tipo(
        tipo
    )

    nome = item.get(
        "name",
        "Item desconhecido"
    )

    preco = formatar_preco(
        item.get(
            "price",
            0
        )
    )

    raridade = item.get(
        "rarity",
        "Desconhecida"
    )

    # ----------------------------------------
    # TÍTULO
    # ----------------------------------------

    embed.title = (
        f"{emoji} {nome}"
    )

    # ----------------------------------------
    # INFORMAÇÕES
    # ----------------------------------------

    embed.description = (
        f"💰 **{preco} V-Bucks**\n"
        f"⭐ {raridade}\n"
        f"📦 {tipo}"
    )

    # ----------------------------------------
    # IMAGEM
    # ----------------------------------------

    imagem = item.get(
        "image"
    )

    if imagem:

        embed.set_image(
            url=imagem
        )

    return embed


# ============================================================
# CRIAR CABEÇALHO
# ============================================================

def criar_cabecalho(
    pagina,
    total_paginas,
    total_itens
):

    agora = datetime.now(
        timezone.utc
    )

    embed = discord.Embed(
        title="🛒 FORTNITE ITEM SHOP",
        description=(
            "Confira os itens disponíveis "
            "na loja de hoje.\n\n"
            "Use os botões abaixo para navegar "
            "pela loja."
        ),
        color=discord.Color.from_rgb(
            88,
            101,
            242
        )
    )

    embed.add_field(
        name="📦 Itens",
        value=f"**{total_itens}**",
        inline=True
    )

    embed.add_field(
        name="📄 Página",
        value=(
            f"**{pagina}/{total_paginas}**"
        ),
        inline=True
    )

    embed.add_field(
        name="🕐 Atualização",
        value=agora.strftime(
            "%d/%m/%Y %H:%M UTC"
        ),
        inline=True
    )

    embed.set_footer(
        text=(
            "Fortnite Item Shop • "
            "Fortnite-API.com"
        )
    )

    return embed


# ============================================================
# VIEW DA LOJA
# ============================================================

class LojaView(
    discord.ui.View
):

    def __init__(
        self,
        itens,
        shop_hash,
        pagina=0
    ):

        super().__init__(
            timeout=None
        )

        self.itens = itens
        self.shop_hash = shop_hash
        self.pagina = pagina

        self.atualizar_botoes()

    # --------------------------------------------------------
    # TOTAL DE PÁGINAS
    # --------------------------------------------------------

    @property
    def total_paginas(self):

        return max(
            1,
            (
                len(self.itens)
                + CARDS_POR_PAGINA
                - 1
            )
            // CARDS_POR_PAGINA
        )

    # --------------------------------------------------------
    # ITENS DA PÁGINA
    # --------------------------------------------------------

    def itens_pagina(self):

        inicio = (
            self.pagina
            * CARDS_POR_PAGINA
        )

        fim = (
            inicio
            + CARDS_POR_PAGINA
        )

        return self.itens[
            inicio:fim
        ]

    # --------------------------------------------------------
    # ATUALIZAR BOTÕES
    # --------------------------------------------------------

    def atualizar_botoes(self):

        self.anterior.disabled = (
            self.pagina <= 0
        )

        self.proximo.disabled = (
            self.pagina
            >= self.total_paginas - 1
        )

    # --------------------------------------------------------
    # MENSAGEM COMPLETA
    # --------------------------------------------------------

    def embeds(self):

        pagina_itens = self.itens_pagina()

        resultado = []

        # Cabeçalho
        resultado.append(
            criar_cabecalho(
                self.pagina + 1,
                self.total_paginas,
                len(self.itens)
            )
        )

        # Quatro cards
        for item in pagina_itens:

            resultado.append(
                criar_card(
                    item
                )
            )

        return resultado

    # --------------------------------------------------------
    # BOTÃO ANTERIOR
    # --------------------------------------------------------

    @discord.ui.button(
        label="◀️",
        style=discord.ButtonStyle.secondary,
        custom_id="fortnite_shop_previous"
    )
    async def anterior(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.pagina > 0:

            self.pagina -= 1

        self.atualizar_botoes()

        await interaction.response.edit_message(
            embeds=self.embeds(),
            view=self
        )

    # --------------------------------------------------------
    # BOTÃO ATUALIZAR
    # --------------------------------------------------------

    @discord.ui.button(
        label="🔄 Atualizar",
        style=discord.ButtonStyle.primary,
        custom_id="fortnite_shop_refresh"
    )
    async def atualizar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.defer()

        dados = await buscar_loja()

        if not dados:

            await interaction.followup.send(
                "❌ Não foi possível consultar a loja.",
                ephemeral=True
            )

            return

        data = dados.get(
            "data",
            {}
        )

        novos_itens = extrair_itens(
            data
        )

        if not novos_itens:

            await interaction.followup.send(
                "❌ Nenhum item encontrado.",
                ephemeral=True
            )

            return

        self.itens = novos_itens

        self.pagina = 0

        self.atualizar_botoes()

        await interaction.message.edit(
            embeds=self.embeds(),
            view=self
        )

    # --------------------------------------------------------
    # BOTÃO PRÓXIMO
    # --------------------------------------------------------

    @discord.ui.button(
        label="▶️",
        style=discord.ButtonStyle.secondary,
        custom_id="fortnite_shop_next"
    )
    async def proximo(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.pagina < (
            self.total_paginas - 1
        ):

            self.pagina += 1

        self.atualizar_botoes()

        await interaction.response.edit_message(
            embeds=self.embeds(),
            view=self
        )


# ============================================================
# ATUALIZAR MENSAGEM DA LOJA
# ============================================================

async def atualizar_mensagem_loja(
    dados,
    forcar=False
):

    global ultima_loja_publicada
    global mensagem_loja_id
    global loja_atual

    if not dados:

        return False

    data = dados.get(
        "data"
    )

    if not isinstance(
        data,
        dict
    ):

        print(
            "Resposta da API inválida."
        )

        return False

    shop_hash = data.get(
        "hash"
    )

    if not shop_hash:

        print(
            "Hash da loja não encontrado."
        )

        return False

    # --------------------------------------------------------
    # VERIFICAR SE A LOJA MUDOU
    # --------------------------------------------------------

    if (
        not forcar
        and shop_hash
        == ultima_loja_publicada
    ):

        print(
            "Loja ainda não mudou."
        )

        return False

    # --------------------------------------------------------
    # EXTRAIR ITENS
    # --------------------------------------------------------

    itens = extrair_itens(
        data
    )

    if not itens:

        print(
            "Nenhum item encontrado."
        )

        return False

    loja_atual = itens

    # --------------------------------------------------------
    # CANAL
    # --------------------------------------------------------

    canal = bot.get_channel(
        CANAL_LOJA_ID
    )

    if canal is None:

        try:

            canal = await bot.fetch_channel(
                CANAL_LOJA_ID
            )

        except Exception as erro:

            print(
                f"Erro acessando canal: {erro}"
            )

            return False

    # --------------------------------------------------------
    # VIEW
    # --------------------------------------------------------

    view = LojaView(
        itens=itens,
        shop_hash=shop_hash,
        pagina=0
    )

    embeds = view.embeds()

    # --------------------------------------------------------
    # BUSCAR MENSAGEM ANTIGA
    # --------------------------------------------------------

    mensagem = None

    if mensagem_loja_id:

        try:

            mensagem = await canal.fetch_message(
                mensagem_loja_id
            )

        except discord.NotFound:

            print(
                "Mensagem anterior não existe mais."
            )

        except discord.HTTPException as erro:

            print(
                f"Erro buscando mensagem: {erro}"
            )

    # --------------------------------------------------------
    # EDITAR MENSAGEM
    # --------------------------------------------------------

    if mensagem:

        try:

            await mensagem.edit(
                embeds=embeds,
                view=view
            )

            salvar_estado(
                shop_hash,
                mensagem.id
            )

            print(
                "✅ Mensagem da loja atualizada."
            )

            return True

        except discord.HTTPException as erro:

            print(
                f"Erro editando mensagem: {erro}"
            )

    # --------------------------------------------------------
    # CRIAR NOVA MENSAGEM
    # --------------------------------------------------------

    try:

        mensagem = await canal.send(
            embeds=embeds,
            view=view
        )

        salvar_estado(
            shop_hash,
            mensagem.id
        )

        print(
            "✅ Nova mensagem da loja criada."
        )

        return True

    except discord.Forbidden:

        print(
            "❌ O bot não possui permissão "
            "para enviar mensagens."
        )

    except discord.HTTPException as erro:

        print(
            f"Erro enviando loja: {erro}"
        )

    return False


# ============================================================
# VERIFICAR LOJA
# ============================================================

async def verificar_loja():

    print(
        "🔎 Verificando loja do Fortnite..."
    )

    dados = await buscar_loja()

    if not dados:

        print(
            "❌ API indisponível."
        )

        return

    data = dados.get(
        "data",
        {}
    )

    shop_hash = data.get(
        "hash"
    )

    if not shop_hash:

        print(
            "❌ Hash não encontrado."
        )

        return

    print(
        f"Hash atual: {shop_hash}"
    )

    print(
        f"Hash salvo: "
        f"{ultima_loja_publicada}"
    )

    # --------------------------------------------------------
    # PRIMEIRA EXECUÇÃO
    # --------------------------------------------------------

    if ultima_loja_publicada is None:

        print(
            "Primeira execução."
        )

        await atualizar_mensagem_loja(
            dados,
            forcar=True
        )

        return

    # --------------------------------------------------------
    # NOVA LOJA
    # --------------------------------------------------------

    if shop_hash != ultima_loja_publicada:

        print(
            "🛒 NOVA LOJA DETECTADA!"
        )

        await atualizar_mensagem_loja(
            dados
        )

    else:

        print(
            "Nenhuma alteração na loja."
        )


# ============================================================
# LOOP AUTOMÁTICO
# ============================================================

@tasks.loop(
    minutes=5
)
async def verificar_loja_loop():

    await verificar_loja()


# ============================================================
# BOT INICIADO
# ============================================================

@bot.event
async def on_ready():

    print("=" * 50)

    print(
        f"Bot conectado como: {bot.user}"
    )

    print(
        f"ID do bot: {bot.user.id}"
    )

    print(
        f"Canal das reações: "
        f"{CANAL_REACOES_ID}"
    )

    print(
        f"Canal da loja: "
        f"{CANAL_LOJA_ID}"
    )

    print("=" * 50)

    carregar_estado()

    if not verificar_loja_loop.is_running():

        verificar_loja_loop.start()


# ============================================================
# MENSAGENS
# ============================================================

@bot.event
async def on_message(
    message
):

    # Não reage a bots
    if message.author.bot:

        return

    # ========================================================
    # CANAL DE REAÇÕES
    # ========================================================

    if (
        message.channel.id
        == CANAL_REACOES_ID
    ):

        try:

            # W
            await message.add_reaction(
                "🟢"
            )

            # Balança
            await message.add_reaction(
                "⚖️"
            )

            # L
            await message.add_reaction(
                "🔴"
            )

            print(
                f"Reações adicionadas na "
                f"mensagem de "
                f"{message.author}."
            )

        except discord.Forbidden:

            print(
                "ERRO: O bot não possui "
                "permissão para adicionar reações."
            )

        except discord.HTTPException as erro:

            print(
                f"Erro do Discord: {erro}"
            )

    # Mantém os comandos funcionando
    await bot.process_commands(
        message
    )


# ============================================================
# COMANDO DE TESTE
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(
    ctx
):

    await ctx.send(
        "🔄 Atualizando a loja..."
    )

    dados = await buscar_loja()

    if not dados:

        await ctx.send(
            "❌ Não consegui consultar a API."
        )

        return

    sucesso = await atualizar_mensagem_loja(
        dados,
        forcar=True
    )

    if sucesso:

        await ctx.send(
            "✅ Loja atualizada com sucesso!"
        )

    else:

        await ctx.send(
            "❌ Não consegui atualizar a loja."
        )


# ============================================================
# ERRO DO COMANDO
# ============================================================

@teste_loja.error
async def teste_loja_error(
    ctx,
    erro
):

    if isinstance(
        erro,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ Você precisa ser administrador."
        )

    else:

        print(
            f"Erro no comando testeloja: {erro}"
        )


# ============================================================
# VERIFICAR TOKEN
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN "
        "não está configurada."
    )


# ============================================================
# INICIAR BOT
# ============================================================

bot.run(
    TOKEN
)