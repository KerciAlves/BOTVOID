import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import io
import json
import os
import hashlib
import math
from datetime import datetime


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# Canal original das reações
CANAL_REACOES_ID = 1556998399461691443

# Canal da Loja Fortnite
CANAL_LOJA_ID = 1214658145243234324

# API
FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"
IDIOMA = "pt-BR"

# Verificação da loja
INTERVALO_VERIFICACAO = 5

# Quantidade de colunas
COLUNAS = 4

# Tamanho de cada card
CARD_LARGURA = 300
CARD_ALTURA = 340

# Espaçamento
ESPACO = 15

# Margens
MARGEM = 30

# Arquivo que guarda o ID da mensagem
SHOP_STATE_FILE = "shop_state.json"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# ESTADO
# ============================================================

ultima_loja_hash = None
mensagem_loja_id = None

loja_atual = []
loja_data = None


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(tamanho, negrito=False):

    if negrito:

        caminhos = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]

    else:

        caminhos = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]

    for caminho in caminhos:

        try:
            return ImageFont.truetype(
                caminho,
                tamanho
            )

        except Exception:
            pass

    return ImageFont.load_default()


# ============================================================
# IMPORTAÇÃO DO PIL
# ============================================================

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# ESTADO
# ============================================================

def carregar_estado():

    global ultima_loja_hash
    global mensagem_loja_id

    if not os.path.exists(SHOP_STATE_FILE):
        return

    try:

        with open(
            SHOP_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            estado = json.load(arquivo)

        ultima_loja_hash = estado.get(
            "shop_hash"
        )

        mensagem_loja_id = estado.get(
            "message_id"
        )

        print(
            "Estado da loja carregado."
        )

    except Exception as erro:

        print(
            f"Erro carregando estado: {erro}"
        )


def salvar_estado():

    try:

        estado = {
            "shop_hash": ultima_loja_hash,
            "message_id": mensagem_loja_id
        }

        with open(
            SHOP_STATE_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                estado,
                arquivo,
                ensure_ascii=False,
                indent=4
            )

    except Exception as erro:

        print(
            f"Erro salvando estado: {erro}"
        )


# ============================================================
# API
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
            ) as resposta:

                if resposta.status != 200:

                    print(
                        f"Erro API: HTTP {resposta.status}"
                    )

                    return None

                return await resposta.json()

    except Exception as erro:

        print(
            f"Erro consultando API: {erro}"
        )

        return None


# ============================================================
# UTILITÁRIOS
# ============================================================

def primeiro_valor(
    dicionario,
    *chaves,
    padrao=None
):

    if not isinstance(
        dicionario,
        dict
    ):
        return padrao

    for chave in chaves:

        valor = dicionario.get(
            chave
        )

        if valor is not None:
            return valor

    return padrao


def obter_nome(item):

    return primeiro_valor(
        item,
        "name",
        "displayName",
        "title",
        padrao="Item"
    )


def obter_imagem(item):

    if not isinstance(
        item,
        dict
    ):
        return None

    imagens = item.get(
        "images"
    )

    if isinstance(
        imagens,
        dict
    ):

        for chave in [
            "featured",
            "icon",
            "background",
            "full_background"
        ]:

            imagem = imagens.get(
                chave
            )

            if (
                isinstance(imagem, str)
                and imagem.startswith("http")
            ):
                return imagem

    for chave in [
        "image",
        "icon",
        "iconUrl"
    ]:

        imagem = item.get(
            chave
        )

        if (
            isinstance(imagem, str)
            and imagem.startswith("http")
        ):
            return imagem

    return None


def obter_tipo(item):

    tipo = item.get(
        "type"
    )

    if isinstance(
        tipo,
        dict
    ):

        return primeiro_valor(
            tipo,
            "displayValue",
            "value",
            "name",
            padrao="Item"
        )

    return (
        item.get("displayType")
        or tipo
        or "Item"
    )


def obter_raridade(item):

    raridade = item.get(
        "rarity"
    )

    if isinstance(
        raridade,
        dict
    ):

        return primeiro_valor(
            raridade,
            "displayValue",
            "value",
            "name",
            padrao=""
        )

    return (
        item.get("displayRarity")
        or raridade
        or ""
    )


def obter_preco(entry):

    preco = primeiro_valor(
        entry,
        "finalPrice",
        "final_price",
        "regularPrice",
        "regular_price",
        "price"
    )

    if isinstance(
        preco,
        dict
    ):

        preco = primeiro_valor(
            preco,
            "finalPrice",
            "price",
            "value"
        )

    if preco is not None:

        try:
            return int(preco)

        except Exception:
            pass

    bundle = entry.get(
        "bundle"
    )

    if isinstance(
        bundle,
        dict
    ):

        preco = primeiro_valor(
            bundle,
            "finalPrice",
            "price"
        )

        if preco is not None:

            try:
                return int(preco)

            except Exception:
                pass

    return None


def formatar_preco(preco):

    if preco is None:
        return "N/D"

    return (
        f"{preco:,}"
        .replace(",", ".")
    )


# ============================================================
# EXTRAIR ITENS
# ============================================================

def extrair_itens(loja):

    if not isinstance(
        loja,
        dict
    ):
        return []

    data = loja.get(
        "data",
        loja
    )

    if not isinstance(
        data,
        dict
    ):
        return []

    entries = data.get(
        "entries",
        []
    )

    if not isinstance(
        entries,
        list
    ):
        return []

    resultado = []

    for entry in entries:

        if not isinstance(
            entry,
            dict
        ):
            continue

        preco = obter_preco(
            entry
        )

        colecoes = [
            "brItems",
            "items",
            "tracks",
            "instruments",
            "cars",
            "legoKits",
            "cosmetics"
        ]

        encontrados = []

        for colecao in colecoes:

            valor = entry.get(
                colecao
            )

            if isinstance(
                valor,
                list
            ):

                encontrados.extend(
                    valor
                )

        # Caso a própria entrada seja um item
        if not encontrados:

            if (
                entry.get("name")
                or entry.get("displayName")
                or entry.get("images")
            ):

                encontrados.append(
                    entry
                )

        for item in encontrados:

            if not isinstance(
                item,
                dict
            ):
                continue

            imagem = obter_imagem(
                item
            )

            if not imagem:
                continue

            resultado.append({

                "name": obter_nome(
                    item
                ),

                "image": imagem,

                "rarity": obter_raridade(
                    item
                ),

                "type": obter_tipo(
                    item
                ),

                "price": preco
            })

    # Remover duplicados
    unicos = []
    vistos = set()

    for item in resultado:

        chave = (
            item["name"],
            item["image"],
            item["price"]
        )

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        unicos.append(
            item
        )

    return unicos


# ============================================================
# RARIDADE
# ============================================================

def cor_raridade(raridade):

    texto = str(
        raridade
    ).lower()

    if "legend" in texto:
        return (255, 190, 45)

    if "epic" in texto:
        return (180, 65, 255)

    if "rare" in texto:
        return (45, 145, 255)

    if "uncommon" in texto:
        return (70, 200, 110)

    if "marvel" in texto:
        return (220, 55, 65)

    if "star wars" in texto:
        return (80, 130, 220)

    if "gaming" in texto:
        return (90, 180, 255)

    return (100, 110, 130)


# ============================================================
# DOWNLOAD DAS IMAGENS
# ============================================================

async def baixar_imagem(
    session,
    url
):

    try:

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=20
            )
        ) as resposta:

            if resposta.status != 200:
                return None

            dados = await resposta.read()

            imagem = Image.open(
                io.BytesIO(dados)
            ).convert(
                "RGB"
            )

            return imagem

    except Exception:

        return None


# ============================================================
# AJUSTAR IMAGEM
# ============================================================

def encaixar_imagem(
    imagem,
    largura,
    altura
):

    if imagem is None:

        return Image.new(
            "RGB",
            (largura, altura),
            (30, 34, 45)
        )

    proporcao_original = (
        imagem.width /
        imagem.height
    )

    proporcao_destino = (
        largura /
        altura
    )

    if proporcao_original > proporcao_destino:

        nova_altura = altura

        nova_largura = int(
            altura *
            proporcao_original
        )

    else:

        nova_largura = largura

        nova_altura = int(
            largura /
            proporcao_original
        )

    imagem = imagem.resize(
        (
            nova_largura,
            nova_altura
        ),
        Image.Resampling.LANCZOS
    )

    esquerda = (
        nova_largura -
        largura
    ) // 2

    topo = (
        nova_altura -
        altura
    ) // 2

    return imagem.crop(
        (
            esquerda,
            topo,
            esquerda + largura,
            topo + altura
        )
    )


# ============================================================
# TEXTO LIMITADO
# ============================================================

def limitar_texto(
    draw,
    texto,
    fonte,
    largura
):

    texto = str(
        texto
    )

    while len(texto) > 1:

        caixa = draw.textbbox(
            (0, 0),
            texto,
            font=fonte
        )

        if (
            caixa[2] -
            caixa[0]
        ) <= largura:

            return texto

        texto = texto[:-1]

    return texto


# ============================================================
# CARD
# ============================================================

def desenhar_card(
    canvas,
    draw,
    item,
    imagem,
    x,
    y
):

    # Card
    draw.rounded_rectangle(
        (
            x,
            y,
            x + CARD_LARGURA,
            y + CARD_ALTURA
        ),
        radius=14,
        fill=(25, 28, 37),
        outline=(65, 70, 85),
        width=2
    )

    cor = cor_raridade(
        item["rarity"]
    )

    # Área da imagem
    imagem_largura = CARD_LARGURA
    imagem_altura = 245

    imagem = encaixar_imagem(
        imagem,
        imagem_largura,
        imagem_altura
    )

    canvas.paste(
        imagem,
        (
            x,
            y
        )
    )

    # Barra de raridade
    draw.rectangle(
        (
            x,
            y,
            x + CARD_LARGURA,
            y + 7
        ),
        fill=cor
    )

    # Fundo inferior
    draw.rectangle(
        (
            x,
            y + 245,
            x + CARD_LARGURA,
            y + CARD_ALTURA
        ),
        fill=(20, 23, 31)
    )

    fonte_nome = carregar_fonte(
        19,
        True
    )

    fonte_tipo = carregar_fonte(
        13,
        False
    )

    fonte_preco = carregar_fonte(
        17,
        True
    )

    nome = limitar_texto(
        draw,
        item["name"],
        fonte_nome,
        CARD_LARGURA - 24
    )

    draw.text(
        (
            x + 12,
            y + 258
        ),
        nome,
        fill=(255, 255, 255),
        font=fonte_nome
    )

    tipo = str(
        item["type"]
    )

    tipo = limitar_texto(
        draw,
        tipo,
        fonte_tipo,
        CARD_LARGURA - 24
    )

    draw.text(
        (
            x + 12,
            y + 286
        ),
        tipo,
        fill=(155, 162, 178),
        font=fonte_tipo
    )

    # V-Bucks
    preco = formatar_preco(
        item["price"]
    )

    draw.text(
        (
            x + 12,
            y + 309
        ),
        f"◉ {preco} V-BUCKS",
        fill=(255, 255, 255),
        font=fonte_preco
    )


# ============================================================
# CRIAR IMAGEM COMPLETA
# ============================================================

async def criar_imagem_loja(
    itens,
    data_loja
):

    linhas = math.ceil(
        len(itens) /
        COLUNAS
    )

    # Cabeçalho
    CABECALHO = 125

    # Rodapé
    RODAPE = 70

    largura = (
        MARGEM * 2
        +
        COLUNAS * CARD_LARGURA
        +
        (COLUNAS - 1) * ESPACO
    )

    altura = (
        CABECALHO
        +
        linhas * CARD_ALTURA
        +
        (linhas - 1) * ESPACO
        +
        RODAPE
        +
        MARGEM
    )

    canvas = Image.new(
        "RGB",
        (
            largura,
            altura
        ),
        (12, 15, 22)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # ========================================================
    # FUNDO
    # ========================================================

    for y in range(
        altura
    ):

        fator = y / altura

        r = int(
            10 + fator * 10
        )

        g = int(
            13 + fator * 13
        )

        b = int(
            21 + fator * 25
        )

        draw.line(
            (
                0,
                y,
                largura,
                y
            ),
            fill=(
                r,
                g,
                b
            )
        )

    # ========================================================
    # TÍTULO
    # ========================================================

    fonte_titulo = carregar_fonte(
        38,
        True
    )

    fonte_subtitulo = carregar_fonte(
        17
    )

    fonte_info = carregar_fonte(
        16
    )

    draw.text(
        (
            MARGEM,
            25
        ),
        "LOJA DE ITENS",
        fill=(255, 255, 255),
        font=fonte_titulo
    )

    draw.text(
        (
            MARGEM + 3,
            75
        ),
        "FORTNITE • LOJA ATUAL",
        fill=(145, 153, 170),
        font=fonte_subtitulo
    )

    # Data
    if data_loja:

        try:

            data_formatada = (
                datetime.fromisoformat(
                    str(data_loja)
                    .replace(
                        "Z",
                        "+00:00"
                    )
                )
                .astimezone()
                .strftime(
                    "%d/%m/%Y %H:%M"
                )
            )

        except Exception:

            data_formatada = str(
                data_loja
            )

    else:

        data_formatada = "Atualizado agora"

    texto_data = (
        f"Atualizado: {data_formatada}"
    )

    caixa = draw.textbbox(
        (
            0,
            0
        ),
        texto_data,
        font=fonte_info
    )

    draw.text(
        (
            largura -
            MARGEM -
            (caixa[2] - caixa[0]),
            40
        ),
        texto_data,
        fill=(170, 176, 190),
        font=fonte_info
    )

    # Linha
    draw.line(
        (
            MARGEM,
            112,
            largura - MARGEM,
            112
        ),
        fill=(60, 66, 80),
        width=2
    )

    # ========================================================
    # BAIXAR IMAGENS
    # ========================================================

    async with aiohttp.ClientSession() as session:

        tarefas = [
            baixar_imagem(
                session,
                item["image"]
            )
            for item in itens
        ]

        imagens = await asyncio.gather(
            *tarefas,
            return_exceptions=True
        )

    # ========================================================
    # DESENHAR TODOS OS CARDS
    # ========================================================

    for indice, item in enumerate(
        itens
    ):

        linha = (
            indice //
            COLUNAS
        )

        coluna = (
            indice %
            COLUNAS
        )

        x = (
            MARGEM
            +
            coluna *
            (
                CARD_LARGURA
                +
                ESPACO
            )
        )

        y = (
            CABECALHO
            +
            linha *
            (
                CARD_ALTURA
                +
                ESPACO
            )
        )

        imagem = imagens[
            indice
        ]

        if isinstance(
            imagem,
            Exception
        ):

            imagem = None

        desenhar_card(
            canvas,
            draw,
            item,
            imagem,
            x,
            y
        )

    # ========================================================
    # RODAPÉ
    # ========================================================

    y_rodape = (
        altura -
        RODAPE +
        15
    )

    draw.line(
        (
            MARGEM,
            y_rodape - 8,
            largura - MARGEM,
            y_rodape - 8
        ),
        fill=(60, 66, 80),
        width=2
    )

    texto = (
        f"{len(itens)} itens na loja"
        " • Atualização automática"
    )

    caixa = draw.textbbox(
        (
            0,
            0
        ),
        texto,
        font=fonte_subtitulo
    )

    draw.text(
        (
            (
                largura -
                (
                    caixa[2] -
                    caixa[0]
                )
            ) / 2,
            y_rodape + 15
        ),
        texto,
        fill=(140, 148, 165),
        font=fonte_subtitulo
    )

    # ========================================================
    # COMPRESSÃO
    # ========================================================

    buffer = io.BytesIO()

    # Se ficar muito grande, reduz um pouco
    if altura > 3500:

        nova_altura = 3500

        nova_largura = int(
            largura *
            (
                nova_altura /
                altura
            )
        )

        canvas = canvas.resize(
            (
                nova_largura,
                nova_altura
            ),
            Image.Resampling.LANCZOS
        )

    canvas.save(
        buffer,
        format="JPEG",
        quality=88,
        optimize=True
    )

    buffer.seek(0)

    return buffer


# ============================================================
# HASH DA LOJA
# ============================================================

def obter_hash_loja(
    loja
):

    if not isinstance(
        loja,
        dict
    ):
        return None

    data = loja.get(
        "data",
        loja
    )

    if not isinstance(
        data,
        dict
    ):
        return None

    shop_hash = data.get(
        "hash"
    )

    if shop_hash:

        return str(
            shop_hash
        )

    entries = data.get(
        "entries",
        []
    )

    try:

        texto = json.dumps(
            entries,
            sort_keys=True,
            ensure_ascii=False
        )

        return hashlib.sha256(
            texto.encode(
                "utf-8"
            )
        ).hexdigest()

    except Exception:

        return None


def obter_data_loja(
    loja
):

    if not isinstance(
        loja,
        dict
    ):
        return None

    data = loja.get(
        "data",
        loja
    )

    if not isinstance(
        data,
        dict
    ):
        return None

    return (
        data.get("date")
        or data.get("lastUpdate")
        or data.get("last_update")
    )


# ============================================================
# ATUALIZAR MENSAGEM
# ============================================================

async def atualizar_mensagem_loja():

    global mensagem_loja_id

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

            return

    imagem = await criar_imagem_loja(
        loja_atual,
        loja_data
    )

    arquivo = discord.File(
        imagem,
        filename="fortnite_loja.jpg"
    )

    embed = discord.Embed(
        color=discord.Color.from_rgb(
            45,
            110,
            220
        )
    )

    embed.set_image(
        url="attachment://fortnite_loja.jpg"
    )

    embed.set_footer(
        text=(
            "Fortnite Item Shop • "
            "Atualização automática"
        )
    )

    mensagem = None

    # ========================================================
    # TENTAR MENSAGEM SALVA
    # ========================================================

    if mensagem_loja_id:

        try:

            mensagem = await canal.fetch_message(
                int(mensagem_loja_id)
            )

        except Exception:

            mensagem = None

    # ========================================================
    # PROCURAR MENSAGEM DO BOT
    # ========================================================

    if mensagem is None:

        try:

            async for msg in canal.history(
                limit=30
            ):

                if (
                    msg.author.id == bot.user.id
                    and msg.embeds
                ):

                    mensagem = msg

                    mensagem_loja_id = msg.id

                    break

        except Exception as erro:

            print(
                f"Erro procurando mensagem: {erro}"
            )

    # ========================================================
    # EDITAR
    # ========================================================

    if mensagem:

        try:

            await mensagem.edit(
                embed=embed,
                attachments=[
                    arquivo
                ]
            )

            print(
                "Mensagem da loja atualizada."
            )

        except Exception as erro:

            print(
                f"Erro editando loja: {erro}"
            )

    # ========================================================
    # CRIAR
    # ========================================================

    else:

        try:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo
            )

            mensagem_loja_id = (
                mensagem.id
            )

            print(
                "Nova mensagem da loja criada."
            )

        except Exception as erro:

            print(
                f"Erro criando mensagem: {erro}"
            )

    salvar_estado()


# ============================================================
# VERIFICAR LOJA
# ============================================================

async def verificar_loja(
    forcar=False
):

    global ultima_loja_hash
    global loja_atual
    global loja_data

    loja = await buscar_loja()

    if loja is None:
        return False

    novo_hash = obter_hash_loja(
        loja
    )

    if not novo_hash:

        print(
            "Não foi possível identificar o hash da loja."
        )

        return False

    mudou = (
        novo_hash !=
        ultima_loja_hash
    )

    if (
        not mudou
        and
        not forcar
    ):

        return False

    itens = extrair_itens(
        loja
    )

    if not itens:

        print(
            "Nenhum item encontrado."
        )

        return False

    loja_atual = itens

    loja_data = obter_data_loja(
        loja
    )

    ultima_loja_hash = (
        novo_hash
    )

    print(
        f"Loja encontrada: {len(itens)} itens"
    )

    print(
        f"Hash: {novo_hash}"
    )

    await atualizar_mensagem_loja()

    salvar_estado()

    return True


# ============================================================
# LOOP
# ============================================================

@tasks.loop(
    minutes=INTERVALO_VERIFICACAO
)
async def verificar_loja_loop():

    print(
        "Verificando Loja Fortnite..."
    )

    await verificar_loja()


@verificar_loja_loop.before_loop
async def antes_loop():

    await bot.wait_until_ready()


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print(
        f"Bot conectado: {bot.user}"
    )

    carregar_estado()

    if not verificar_loja_loop.is_running():

        verificar_loja_loop.start()

    await verificar_loja()


# ============================================================
# REAÇÕES
# ============================================================

@bot.event
async def on_message(
    message
):

    if message.author.bot:
        return

    # ========================================================
    # SISTEMA ORIGINAL — MANTIDO
    # ========================================================

    if (
        message.channel.id ==
        CANAL_REACOES_ID
    ):

        try:

            await message.add_reaction(
                "🟢"
            )

            await message.add_reaction(
                "⚖️"
            )

            await message.add_reaction(
                "🔴"
            )

        except Exception as erro:

            print(
                f"Erro adicionando reações: {erro}"
            )

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
        "🔄 Buscando a loja atual..."
    )

    sucesso = await verificar_loja(
        forcar=True
    )

    if sucesso:

        await ctx.send(
            "✅ Loja atualizada!"
        )

    else:

        await ctx.send(
            "❌ Não foi possível atualizar a loja."
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


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN não foi configurado."
    )


bot.run(TOKEN)