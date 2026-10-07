import os
import gc
import json
import asyncio
import tempfile
from io import BytesIO
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURAÇÃO
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CANAL_REACOES_ID = 1556998399461691443
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

IDIOMA = "pt-BR"

INTERVALO_VERIFICACAO = 300  # 5 minutos

SHOP_STATE_FILE = "shop_state.json"

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

# Limite de segurança para imagens baixadas
MAX_IMAGE_BYTES = 700_000

# Tamanho máximo da imagem enviada ao Discord
IMAGEM_LARGURA = 1200

# Máximo de itens exibidos
MAX_ITENS = 40


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(tamanho, negrito=False):
    if negrito:
        caminhos = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    else:
        caminhos = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

    for caminho in caminhos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            pass

    return ImageFont.load_default()


FONT_TITULO = carregar_fonte(38, True)
FONT_SUBTITULO = carregar_fonte(17, True)
FONT_NOME = carregar_fonte(17, True)
FONT_RARIDADE = carregar_fonte(11, True)
FONT_PRECO = carregar_fonte(20, True)
FONT_RODAPE = carregar_fonte(11, True)
FONT_PEQUENA = carregar_fonte(10, False)


# ============================================================
# CORES DAS RARIDADES
# ============================================================

CORES_RARIDADE = {
    "common": (150, 150, 160),
    "uncommon": (50, 205, 100),
    "rare": (50, 135, 255),
    "epic": (185, 65, 255),
    "legendary": (255, 165, 45),
    "mythic": (255, 210, 55),
    "icon": (240, 205, 75),
    "default": (80, 130, 200),
}


def cor_raridade(nome):
    texto = str(nome or "").lower()

    if "lend" in texto or "legend" in texto:
        return CORES_RARIDADE["legendary"]

    if "épico" in texto or "epic" in texto:
        return CORES_RARIDADE["epic"]

    if "raro" in texto or "rare" in texto:
        return CORES_RARIDADE["rare"]

    if "incomum" in texto or "uncommon" in texto:
        return CORES_RARIDADE["uncommon"]

    if "mítico" in texto or "mythic" in texto:
        return CORES_RARIDADE["mythic"]

    if "ícone" in texto or "icon" in texto:
        return CORES_RARIDADE["icon"]

    if "comum" in texto or "common" in texto:
        return CORES_RARIDADE["common"]

    return CORES_RARIDADE["default"]


# ============================================================
# UTILITÁRIOS
# ============================================================

def limitar_texto(texto, limite):
    texto = str(texto or "")

    if len(texto) <= limite:
        return texto

    return texto[:limite - 3] + "..."


def texto_centralizado(draw, caixa, texto, fonte, cor):
    x1, y1, x2, y2 = caixa

    bbox = draw.textbbox(
        (0, 0),
        texto,
        font=fonte
    )

    largura = bbox[2] - bbox[0]
    altura = bbox[3] - bbox[1]

    x = x1 + ((x2 - x1) - largura) / 2
    y = y1 + ((y2 - y1) - altura) / 2 - bbox[1]

    draw.text(
        (int(x), int(y)),
        texto,
        font=fonte,
        fill=cor
    )


def parse_data(valor):
    if not valor:
        return None

    try:
        texto = str(valor)

        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"

        data = datetime.fromisoformat(texto)

        if data.tzinfo is None:
            data = data.replace(
                tzinfo=timezone.utc
            )

        return data

    except Exception:
        return None


# ============================================================
# ESTADO
# ============================================================

def carregar_estado():
    if not os.path.exists(SHOP_STATE_FILE):
        return {}

    try:
        with open(
            SHOP_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:
            return json.load(arquivo)

    except Exception:
        return {}


def salvar_estado(estado):
    try:
        arquivo_temporario = SHOP_STATE_FILE + ".tmp"

        with open(
            arquivo_temporario,
            "w",
            encoding="utf-8"
        ) as arquivo:
            json.dump(
                estado,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            arquivo_temporario,
            SHOP_STATE_FILE
        )

    except Exception as erro:
        print(
            f"[STATE] Erro ao salvar: {erro}"
        )


# ============================================================
# BUSCAR LOJA
# ============================================================

async def buscar_loja():
    timeout = aiohttp.ClientTimeout(
        total=20
    )

    headers = {
        "User-Agent": "VoidHelper/1.0"
    }

    params = {
        "language": IDIOMA
    }

    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers
        ) as session:

            async with session.get(
                FORTNITE_SHOP_URL,
                params=params
            ) as resposta:

                if resposta.status != 200:
                    print(
                        f"[API] HTTP {resposta.status}"
                    )
                    return None

                return await resposta.json()

    except Exception as erro:
        print(
            f"[API] Erro: {erro}"
        )
        return None


# ============================================================
# EXTRAIR ITENS
# ============================================================

def extrair_itens(data):
    dados = data.get(
        "data",
        {}
    )

    entries = dados.get(
        "entries",
        []
    )

    agora = datetime.now(
        timezone.utc
    )

    itens = []
    ids_adicionados = set()

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        in_date = parse_data(
            entry.get("inDate")
        )

        out_date = parse_data(
            entry.get("outDate")
        )

        # Oferta futura
        if in_date and in_date > agora:
            continue

        # Oferta expirada
        if out_date and out_date < agora:
            continue

        br_items = entry.get(
            "brItems"
        ) or []

        if not br_items:
            continue

        preco = entry.get(
            "finalPrice"
        )

        if preco is None:
            preco = entry.get(
                "regularPrice",
                0
            )

        for item in br_items:

            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            nome = item.get("name")

            if not nome:
                continue

            chave = item_id or nome

            if chave in ids_adicionados:
                continue

            ids_adicionados.add(chave)

            tipo = item.get(
                "type"
            ) or {}

            if isinstance(tipo, dict):
                raridade = tipo.get(
                    "displayValue",
                    ""
                )
            else:
                raridade = ""

            imagens = item.get(
                "images"
            ) or {}

            imagem_url = (
                imagens.get("featured")
                or imagens.get("icon")
                or imagens.get("smallIcon")
            )

            itens.append({
                "id": item_id,
                "name": nome,
                "rarity": raridade,
                "image": imagem_url,
                "price": preco,
                "inDate": (
                    in_date.isoformat()
                    if in_date
                    else None
                ),
                "offerId": entry.get(
                    "offerId"
                ),
            })

            if len(itens) >= MAX_ITENS:
                break

        if len(itens) >= MAX_ITENS:
            break

    return itens


# ============================================================
# DOWNLOAD DE IMAGEM
# ============================================================

async def baixar_imagem(session, url):
    if not url:
        return None

    try:
        timeout = aiohttp.ClientTimeout(
            total=8
        )

        async with session.get(
            url,
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:
                return None

            tamanho = resposta.content_length

            if tamanho and tamanho > MAX_IMAGE_BYTES:
                return None

            dados = await resposta.read()

            if len(dados) > MAX_IMAGE_BYTES:
                return None

            return dados

    except Exception as erro:
        print(
            f"[DOWNLOAD] Erro: {erro}"
        )
        return None


# ============================================================
# FUNDO GAMER LEVE
# ============================================================

def criar_fundo(largura, altura):
    # RGB = 3 bytes por pixel.
    # Muito mais econômico que RGBA.
    imagem = Image.new(
        "RGB",
        (largura, altura),
        (7, 10, 24)
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # Faixas horizontais simples
    for y in range(
        0,
        altura,
        30
    ):
        valor = int(
            15 + (
                20 * y / max(1, altura)
            )
        )

        draw.line(
            (
                0,
                y,
                largura,
                y
            ),
            fill=(
                7,
                12,
                valor
            ),
            width=1
        )

    # Linhas diagonais gamer
    for x in range(
        -altura,
        largura,
        150
    ):
        draw.line(
            (
                x,
                altura,
                x + altura,
                0
            ),
            fill=(18, 28, 55),
            width=1
        )

    # Pequenas partículas
    pontos = [
        (80, 60),
        (220, 120),
        (390, 70),
        (560, 105),
        (740, 65),
        (910, 130),
        (1090, 80),
        (1150, 180),
        (130, 420),
        (480, 520),
        (830, 430),
        (1080, 570),
    ]

    for x, y in pontos:
        if x < largura and y < altura:
            draw.ellipse(
                (
                    x,
                    y,
                    x + 3,
                    y + 3
                ),
                fill=(60, 130, 220)
            )

    return imagem


# ============================================================
# V-BUCKS
# ============================================================

def desenhar_vbucks(
    draw,
    x,
    y,
    tamanho=16
):
    metade = tamanho // 2

    pontos = [
        (x, y - metade),
        (x + metade, y),
        (x, y + metade),
        (x - metade, y),
    ]

    draw.polygon(
        pontos,
        fill=(80, 190, 245),
        outline=(220, 245, 255)
    )

    draw.line(
        (
            x,
            y - 5,
            x,
            y + 5
        ),
        fill=(255, 255, 255),
        width=2
    )


# ============================================================
# GERAR IMAGEM
# ============================================================

async def gerar_imagem_loja(
    itens,
    data_loja
):
    if not itens:
        return None

    # --------------------------------------------------------
    # DIMENSÕES
    # --------------------------------------------------------

    largura = IMAGEM_LARGURA

    colunas = 4

    margem = 30

    espaco = 14

    topo = 150

    rodape = 55

    card_largura = (
        largura
        - (margem * 2)
        - (espaco * 3)
    ) // 4

    card_altura = 340

    linhas = (
        len(itens)
        + colunas
        - 1
    ) // colunas

    altura = (
        margem
        + topo
        + (
            linhas
            * card_altura
        )
        + (
            max(0, linhas - 1)
            * espaco
        )
        + rodape
    )

    # --------------------------------------------------------
    # FUNDO
    # --------------------------------------------------------

    imagem = criar_fundo(
        largura,
        altura
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            largura,
            topo
        ),
        fill=(5, 8, 20)
    )

    # Barra azul
    draw.rectangle(
        (
            0,
            topo - 4,
            largura,
            topo
        ),
        fill=(55, 145, 255)
    )

    # Linha decorativa
    draw.line(
        (
            margem,
            22,
            largura - margem,
            22
        ),
        fill=(30, 65, 120),
        width=1
    )

    texto_centralizado(
        draw,
        (
            0,
            30,
            largura,
            76
        ),
        "FORTNITE ITEM SHOP",
        FONT_TITULO,
        (240, 247, 255)
    )

    # Data
    texto_data = "ATUALIZAÇÃO DA LOJA"

    if data_loja:
        data = parse_data(
            data_loja
        )

        if data:
            data_br = data.astimezone(
                FUSO_BRASIL
            )

            texto_data = (
                "ATUALIZAÇÃO • "
                + data_br.strftime(
                    "%d/%m/%Y • %H:%M"
                )
            )

    texto_centralizado(
        draw,
        (
            0,
            80,
            largura,
            112
        ),
        texto_data,
        FONT_SUBTITULO,
        (100, 190, 255)
    )

    # Contador
    contador = f"{len(itens)} ITENS"

    bbox = draw.textbbox(
        (0, 0),
        contador,
        font=FONT_PEQUENA
    )

    contador_largura = (
        bbox[2] - bbox[0]
    )

    cx2 = largura - margem
    cx1 = (
        cx2
        - contador_largura
        - 24
    )

    draw.rounded_rectangle(
        (
            cx1,
            118,
            cx2,
            140
        ),
        radius=10,
        fill=(15, 28, 55),
        outline=(45, 115, 210)
    )

    draw.text(
        (
            cx1 + 12,
            123
        ),
        contador,
        font=FONT_PEQUENA,
        fill=(150, 210, 255)
    )

    # --------------------------------------------------------
    # CONEXÃO HTTP
    # --------------------------------------------------------

    timeout = aiohttp.ClientTimeout(
        total=10
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={
            "User-Agent": "VoidHelper/1.0"
        }
    ) as session:

        # ----------------------------------------------------
        # CARDS
        # ----------------------------------------------------

        for indice, item in enumerate(itens):

            coluna = (
                indice % colunas
            )

            linha = (
                indice // colunas
            )

            x = (
                margem
                + coluna
                * (
                    card_largura
                    + espaco
                )
            )

            y = (
                margem
                + topo
                + linha
                * (
                    card_altura
                    + espaco
                )
            )

            cor = cor_raridade(
                item.get(
                    "rarity"
                )
            )

            # ------------------------------------------------
            # CARD
            # ------------------------------------------------

            draw.rounded_rectangle(
                (
                    x,
                    y,
                    x + card_largura,
                    y + card_altura
                ),
                radius=14,
                fill=(12, 16, 31),
                outline=(
                    cor[0],
                    cor[1],
                    cor[2]
                ),
                width=2
            )

            # Faixa superior da raridade
            draw.rounded_rectangle(
                (
                    x + 1,
                    y + 1,
                    x + card_largura - 1,
                    y + 8
                ),
                radius=7,
                fill=cor
            )

            # ------------------------------------------------
            # ÁREA DA IMAGEM
            # ------------------------------------------------

            img_x1 = x + 12
            img_y1 = y + 18
            img_x2 = (
                x
                + card_largura
                - 12
            )
            img_y2 = y + 218

            draw.rounded_rectangle(
                (
                    img_x1,
                    img_y1,
                    img_x2,
                    img_y2
                ),
                radius=10,
                fill=(7, 10, 23),
                outline=(25, 40, 70)
            )

            # ------------------------------------------------
            # IMAGEM DO ITEM
            # ------------------------------------------------

            dados_imagem = await baixar_imagem(
                session,
                item.get("image")
            )

            if dados_imagem:

                item_img = None

                try:
                    item_img = Image.open(
                        BytesIO(dados_imagem)
                    ).convert("RGBA")

                    item_img.thumbnail(
                        (
                            img_x2 - img_x1 - 14,
                            img_y2 - img_y1 - 14
                        ),
                        Image.Resampling.LANCZOS
                    )

                    pos_x = (
                        img_x1
                        + (
                            (
                                img_x2
                                - img_x1
                            )
                            - item_img.width
                        ) // 2
                    )

                    pos_y = (
                        img_y1
                        + (
                            (
                                img_y2
                                - img_y1
                            )
                            - item_img.height
                        ) // 2
                    )

                    imagem.paste(
                        item_img,
                        (
                            pos_x,
                            pos_y
                        ),
                        item_img
                    )

                    del item_img

                except Exception as erro:
                    print(
                        f"[IMAGEM] "
                        f"Erro ao processar: {erro}"
                    )

                finally:
                    del dados_imagem
                    gc.collect()

            # ------------------------------------------------
            # RARIDADE
            # ------------------------------------------------

            raridade = limitar_texto(
                item.get(
                    "rarity",
                    "ITEM"
                ).upper(),
                18
            )

            texto_centralizado(
                draw,
                (
                    x + 12,
                    y + 228,
                    x + card_largura - 12,
                    y + 250
                ),
                raridade,
                FONT_RARIDADE,
                cor
            )

            # ------------------------------------------------
            # NOME
            # ------------------------------------------------

            nome = limitar_texto(
                item.get(
                    "name",
                    "Item"
                ),
                25
            )

            texto_centralizado(
                draw,
                (
                    x + 12,
                    y + 252,
                    x + card_largura - 12,
                    y + 286
                ),
                nome,
                FONT_NOME,
                (240, 245, 255)
            )

            # ------------------------------------------------
            # PREÇO
            # ------------------------------------------------

            try:
                preco = int(
                    item.get(
                        "price",
                        0
                    )
                )
            except Exception:
                preco = 0

            preco_texto = (
                f"{preco:,}".replace(
                    ",",
                    "."
                )
            )

            preco_bbox = draw.textbbox(
                (0, 0),
                preco_texto,
                font=FONT_PRECO
            )

            preco_largura = (
                preco_bbox[2]
                - preco_bbox[0]
            )

            grupo_largura = (
                preco_largura + 30
            )

            preco_x = (
                x
                + (
                    card_largura
                    - grupo_largura
                ) // 2
            )

            preco_y = y + 302

            desenhar_vbucks(
                draw,
                preco_x + 9,
                preco_y + 10,
                17
            )

            draw.text(
                (
                    preco_x + 24,
                    preco_y
                ),
                preco_texto,
                font=FONT_PRECO,
                fill=(105, 210, 255)
            )

            # ------------------------------------------------
            # LIBERA MEMÓRIA
            # ------------------------------------------------

            gc.collect()

    # --------------------------------------------------------
    # RODAPÉ
    # --------------------------------------------------------

    rodape_y = (
        altura - rodape + 16
    )

    draw.line(
        (
            margem,
            rodape_y - 8,
            largura - margem,
            rodape_y - 8
        ),
        fill=(30, 55, 95),
        width=1
    )

    draw.text(
        (
            margem,
            rodape_y
        ),
        "VOIDHELPER",
        font=FONT_RODAPE,
        fill=(80, 180, 255)
    )

    texto_final = (
        "FORTNITE SHOP • ATUALIZAÇÃO AUTOMÁTICA"
    )

    bbox = draw.textbbox(
        (0, 0),
        texto_final,
        font=FONT_PEQUENA
    )

    draw.text(
        (
            largura
            - margem
            - (
                bbox[2]
                - bbox[0]
            ),
            rodape_y + 2
        ),
        texto_final,
        font=FONT_PEQUENA,
        fill=(100, 115, 145)
    )

    # --------------------------------------------------------
    # SALVAR
    # --------------------------------------------------------

    arquivo = tempfile.NamedTemporaryFile(
        suffix=".jpg",
        delete=False
    )

    caminho = arquivo.name
    arquivo.close()

    imagem.save(
        caminho,
        "JPEG",
        quality=68
    )

    del draw
    del imagem

    gc.collect()

    return caminho


# ============================================================
# ATUALIZAR LOJA
# ============================================================

async def atualizar_loja():

    await bot.wait_until_ready()

    print(
        "[LOJA] Sistema iniciado."
    )

    while not bot.is_closed():

        try:

            dados = await buscar_loja()

            if not dados:
                print(
                    "[LOJA] API indisponível."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            data = dados.get(
                "data",
                {}
            )

            shop_hash = data.get(
                "hash"
            )

            data_loja = data.get(
                "date"
            )

            if not shop_hash:

                print(
                    "[LOJA] Hash não encontrado."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            estado = carregar_estado()

            hash_anterior = estado.get(
                "shop_hash"
            )

            # ------------------------------------------------
            # NÃO MUDOU
            # ------------------------------------------------

            if hash_anterior == shop_hash:

                print(
                    "[LOJA] Sem atualização."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            print(
                "[LOJA] Nova atualização encontrada!"
            )

            # ------------------------------------------------
            # ITENS
            # ------------------------------------------------

            itens = extrair_itens(
                dados
            )

            print(
                f"[LOJA] "
                f"{len(itens)} itens encontrados."
            )

            if not itens:

                print(
                    "[LOJA] Nenhum item válido."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            # ------------------------------------------------
            # GERAR
            # ------------------------------------------------

            caminho = await gerar_imagem_loja(
                itens,
                data_loja
            )

            if not caminho:

                print(
                    "[LOJA] Falha na imagem."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            # ------------------------------------------------
            # CANAL
            # ------------------------------------------------

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
                        f"[LOJA] "
                        f"Erro canal: {erro}"
                    )

                    try:
                        os.remove(caminho)
                    except Exception:
                        pass

                    await asyncio.sleep(
                        INTERVALO_VERIFICACAO
                    )
                    continue

            # ------------------------------------------------
            # MENSAGEM ANTERIOR
            # ------------------------------------------------

            mensagem = None

            mensagem_id = estado.get(
                "message_id"
            )

            if mensagem_id:

                try:

                    mensagem = (
                        await canal.fetch_message(
                            int(mensagem_id)
                        )
                    )

                except Exception:
                    mensagem = None

            # ------------------------------------------------
            # ENVIAR
            # ------------------------------------------------

            arquivo = discord.File(
                caminho,
                filename="fortnite-shop.jpg"
            )

            texto = (
                "🎮 **FORTNITE ITEM SHOP**\n"
                "⚡ **Nova atualização da loja!**\n\n"
                f"🛍️ **{len(itens)} itens**\n"
                "🤖 Atualizado automaticamente pelo VoidHelper."
            )

            try:

                if mensagem:

                    await mensagem.edit(
                        content=texto,
                        attachments=[
                            arquivo
                        ]
                    )

                    print(
                        "[LOJA] Mensagem editada."
                    )

                else:

                    mensagem = await canal.send(
                        content=texto,
                        file=arquivo
                    )

                    print(
                        "[LOJA] Mensagem criada."
                    )

            except Exception as erro:

                print(
                    f"[LOJA] "
                    f"Erro Discord: {erro}"
                )

                try:
                    os.remove(caminho)
                except Exception:
                    pass

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )
                continue

            # ------------------------------------------------
            # SALVAR ESTADO
            # ------------------------------------------------

            salvar_estado({
                "shop_hash": shop_hash,
                "message_id": mensagem.id,
                "shop_date": data_loja,
                "items_count": len(itens),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat()
            })

            # ------------------------------------------------
            # LIMPAR
            # ------------------------------------------------

            try:
                os.remove(caminho)
            except Exception:
                pass

            gc.collect()

            print(
                "[LOJA] Atualização concluída."
            )

        except Exception as erro:

            print(
                f"[LOJA] Erro geral: {erro}"
            )

            gc.collect()

        await asyncio.sleep(
            INTERVALO_VERIFICACAO
        )


# ============================================================
# REAÇÕES
# ============================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id == CANAL_REACOES_ID:

        try:

            await message.add_reaction("🟢")
            await message.add_reaction("⚖️")
            await message.add_reaction("🔴")

        except discord.HTTPException as erro:

            print(
                f"[REAÇÕES] Erro: {erro}"
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
async def teste_loja(ctx):

    mensagem = await ctx.send(
        "🔄 Gerando preview da loja..."
    )

    try:

        dados = await buscar_loja()

        if not dados:

            await mensagem.edit(
                content=(
                    "❌ Não consegui acessar "
                    "a API da Fortnite."
                )
            )

            return

        data = dados.get(
            "data",
            {}
        )

        itens = extrair_itens(
            dados
        )

        if not itens:

            await mensagem.edit(
                content=(
                    "⚠️ A API respondeu, "
                    "mas nenhum item válido "
                    "foi encontrado."
                )
            )

            return

        print(
            f"[TESTE] "
            f"Gerando {len(itens)} itens..."
        )

        caminho = await gerar_imagem_loja(
            itens,
            data.get("date")
        )

        if not caminho:

            await mensagem.edit(
                content=(
                    "❌ Não foi possível "
                    "gerar a imagem."
                )
            )

            return

        arquivo = discord.File(
            caminho,
            filename="fortnite-shop.jpg"
        )

        await mensagem.edit(
            content=(
                "🎮 **PREVIEW DA ITEM SHOP**\n"
                f"🔥 {len(itens)} itens encontrados."
            ),
            attachments=[
                arquivo
            ]
        )

        try:
            os.remove(caminho)
        except Exception:
            pass

        gc.collect()

    except Exception as erro:

        print(
            f"[TESTE] Erro: {erro}"
        )

        await mensagem.edit(
            content=(
                "❌ Erro durante o teste:\n"
                f"`{erro}`"
            )
        )


# ============================================================
# ERRO DE PERMISSÃO
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
            "❌ Você precisa ser administrador "
            "para usar esse comando."
        )


# ============================================================
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        "======================================"
    )

    print(
        f"🤖 Bot conectado: {bot.user}"
    )

    print(
        f"🆔 ID: {bot.user.id}"
    )

    print(
        "🎮 Fortnite Shop: ONLINE"
    )

    print(
        "🟢 Sistema de reações: ONLINE"
    )

    print(
        "💾 Modo econômico de memória: ONLINE"
    )

    print(
        "======================================"
    )

    if (
        not hasattr(
            bot,
            "loja_task"
        )
        or bot.loja_task.done()
    ):

        bot.loja_task = asyncio.create_task(
            atualizar_loja()
        )


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN "
        "não foi encontrada."
    )


bot.run(TOKEN)