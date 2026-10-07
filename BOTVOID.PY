import discord
from discord.ext import commands
import aiohttp
import asyncio
import gc
import json
import os
import random
import tempfile
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# CONFIGURAÇÃO
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CANAL_REACOES_ID = 1556998399461691443
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

INTERVALO_VERIFICACAO = 300  # 5 minutos

SHOP_STATE_FILE = "shop_state.json"

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

IDIOMA = "pt-BR"


# ============================================================
# CONFIGURAÇÃO DO DISCORD
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
    caminhos = []

    if negrito:
        caminhos = [
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        caminhos = [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for caminho in caminhos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue

    return ImageFont.load_default()


FONT_TITULO = carregar_fonte(46, True)
FONT_SUBTITULO = carregar_fonte(20, True)
FONT_NOME = carregar_fonte(19, True)
FONT_RARIDADE = carregar_fonte(13, True)
FONT_PRECO = carregar_fonte(23, True)
FONT_PEQUENA = carregar_fonte(12, False)
FONT_RODAPE = carregar_fonte(13, True)


# ============================================================
# CORES DAS RARIDADES
# ============================================================

CORES_RARIDADE = {
    "common": (155, 155, 155),
    "uncommon": (46, 210, 100),
    "rare": (60, 145, 255),
    "epic": (185, 70, 255),
    "legendary": (255, 165, 45),
    "mythic": (255, 210, 55),
    "icon": (245, 205, 75),
    "dark": (80, 80, 90),
}


def cor_raridade(nome):
    if not nome:
        return CORES_RARIDADE["dark"]

    texto = nome.lower()

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

    return CORES_RARIDADE["dark"]


# ============================================================
# FUNÇÕES VISUAIS
# ============================================================

def texto_centralizado(draw, caixa, texto, fonte, fill):
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
        (x, y),
        texto,
        font=fonte,
        fill=fill
    )


def limitar_texto(texto, limite):
    texto = str(texto or "")

    if len(texto) <= limite:
        return texto

    return texto[:limite - 3] + "..."


def criar_gradiente(largura, altura):
    imagem = Image.new("RGB", (largura, altura))
    pixels = imagem.load()

    for y in range(altura):
        proporcao = y / max(1, altura - 1)

        r = int(7 + 8 * proporcao)
        g = int(10 + 8 * proporcao)
        b = int(24 + 30 * proporcao)

        for x in range(largura):
            brilho = int(5 * (x / max(1, largura)))

            pixels[x, y] = (
                min(255, r + brilho),
                min(255, g + brilho),
                min(255, b + brilho),
            )

    return imagem


def adicionar_glow(imagem, posicao, raio=35, intensidade=80):
    camada = Image.new(
        "RGBA",
        imagem.size,
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(camada)

    x, y = posicao

    draw.ellipse(
        (
            x - raio,
            y - raio,
            x + raio,
            y + raio
        ),
        fill=(40, 120, 255, intensidade)
    )

    camada = camada.filter(
        ImageFilter.GaussianBlur(raio // 2)
    )

    imagem.alpha_composite(camada)


def desenhar_particulas(imagem):
    draw = ImageDraw.Draw(imagem)

    largura, altura = imagem.size

    random.seed(2026)

    for _ in range(85):
        x = random.randint(0, largura - 1)
        y = random.randint(0, altura - 1)

        tamanho = random.choice([1, 1, 1, 2, 2, 3])

        draw.ellipse(
            (
                x,
                y,
                x + tamanho,
                y + tamanho
            ),
            fill=(
                90,
                150,
                255,
                random.randint(40, 130)
            )
        )


def desenhar_linhas_gamer(imagem):
    draw = ImageDraw.Draw(imagem)

    largura, altura = imagem.size

    for i in range(-altura, largura, 120):
        draw.line(
            (
                i,
                altura,
                i + altura,
                0
            ),
            fill=(35, 50, 95, 70),
            width=1
        )


# ============================================================
# ÍCONE DE V-BUCKS
# ============================================================

def desenhar_vbucks(draw, x, y, tamanho=18):
    pontos = [
        (x, y - tamanho // 2),
        (x + tamanho // 2, y),
        (x, y + tamanho // 2),
        (x - tamanho // 2, y),
    ]

    draw.polygon(
        pontos,
        fill=(95, 210, 255),
        outline=(220, 245, 255)
    )

    draw.line(
        (
            x,
            y - tamanho // 3,
            x,
            y + tamanho // 3
        ),
        fill=(255, 255, 255),
        width=2
    )


# ============================================================
# DOWNLOAD DA IMAGEM DO ITEM
# ============================================================

async def baixar_imagem(session, url):
    if not url:
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=10)

        async with session.get(
            url,
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:
                return None

            dados = await resposta.read()

            # Evita consumir muita RAM com imagens gigantes
            if len(dados) > 1_000_000:
                return None

            return dados

    except Exception as erro:
        print(f"[IMAGEM] Erro: {erro}")
        return None


# ============================================================
# PARSE DE DATA
# ============================================================

def parse_data(valor):
    if not valor:
        return None

    try:
        texto = str(valor)

        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"

        data = datetime.fromisoformat(texto)

        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)

        return data

    except Exception:
        return None


# ============================================================
# EXTRAÇÃO DOS ITENS DA LOJA
# ============================================================

def extrair_itens_atualizacao(data):
    dados = data.get("data", {})

    entries = dados.get("entries", [])

    agora = datetime.now(timezone.utc)

    itens = []

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        in_date = parse_data(
            entry.get("inDate")
        )

        out_date = parse_data(
            entry.get("outDate")
        )

        # ----------------------------------------------------
        # IGNORA ofertas futuras
        # ----------------------------------------------------

        if in_date and in_date > agora:
            continue

        # ----------------------------------------------------
        # IGNORA ofertas expiradas
        # ----------------------------------------------------

        if out_date and out_date < agora:
            continue

        # ----------------------------------------------------
        # ITENS
        # ----------------------------------------------------

        br_items = entry.get("brItems") or []

        if not br_items:
            continue

        preco = entry.get("finalPrice")

        if preco is None:
            preco = entry.get("regularPrice", 0)

        for item in br_items:

            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            nome = item.get("name")

            if not nome:
                continue

            tipo = item.get("type") or {}

            raridade = ""

            if isinstance(tipo, dict):
                raridade = tipo.get(
                    "displayValue",
                    ""
                )

            imagens = item.get("images") or {}

            imagem_url = (
                imagens.get("featured")
                or imagens.get("icon")
                or imagens.get("smallIcon")
            )

            item_info = {
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
                "offerId": entry.get("offerId"),
            }

            itens.append(item_info)

    # --------------------------------------------------------
    # REMOVE DUPLICADOS
    # --------------------------------------------------------

    unicos = {}

    for item in itens:

        chave = (
            item.get("id")
            or item.get("offerId")
            or item.get("name")
        )

        if chave not in unicos:
            unicos[chave] = item

    itens = list(unicos.values())

    # --------------------------------------------------------
    # ORDENAÇÃO
    # --------------------------------------------------------

    itens.sort(
        key=lambda x: (
            x.get("rarity") or "",
            x.get("name") or ""
        )
    )

    return itens


# ============================================================
# GERAR IMAGEM DA LOJA
# ============================================================

async def gerar_imagem_loja(itens, data_loja):
    if not itens:
        return None

    # --------------------------------------------------------
    # DIMENSÕES
    # --------------------------------------------------------

    largura = 1400

    colunas = 4

    margem = 40

    espaco = 20

    topo = 175

    rodape = 65

    card_largura = (
        largura
        - (margem * 2)
        - (espaco * (colunas - 1))
    ) // colunas

    card_altura = 390

    linhas = (
        len(itens) + colunas - 1
    ) // colunas

    altura = (
        topo
        + (linhas * card_altura)
        + ((linhas - 1) * espaco)
        + rodape
        + margem
    )

    # --------------------------------------------------------
    # FUNDO
    # --------------------------------------------------------

    base = criar_gradiente(
        largura,
        altura
    ).convert("RGBA")

    desenhar_linhas_gamer(base)
    desenhar_particulas(base)

    # Glow no topo
    adicionar_glow(
        base,
        (largura // 2, 55),
        raio=180,
        intensidade=45
    )

    draw = ImageDraw.Draw(
        base,
        "RGBA"
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            largura,
            topo - 10
        ),
        fill=(5, 7, 20, 180)
    )

    # linha luminosa
    draw.rectangle(
        (
            0,
            topo - 10,
            largura,
            topo - 7
        ),
        fill=(60, 150, 255, 220)
    )

    titulo = "FORTNITE ITEM SHOP"

    texto_centralizado(
        draw,
        (0, 18, largura, 70),
        titulo,
        FONT_TITULO,
        (235, 245, 255, 255)
    )

    data_formatada = "ATUALIZAÇÃO DA LOJA"

    if data_loja:
        data = parse_data(data_loja)

        if data:
            data_br = data.astimezone(
                FUSO_BRASIL
            )

            data_formatada = (
                f"ATUALIZAÇÃO • "
                f"{data_br.strftime('%d/%m/%Y')} "
                f"• {data_br.strftime('%H:%M')}"
            )

    texto_centralizado(
        draw,
        (0, 72, largura, 110),
        data_formatada,
        FONT_SUBTITULO,
        (110, 190, 255, 255)
    )

    # contador
    contador = f"{len(itens)} ITENS"

    bbox = draw.textbbox(
        (0, 0),
        contador,
        font=FONT_PEQUENA
    )

    contador_largura = (
        bbox[2] - bbox[0]
    )

    draw.rounded_rectangle(
        (
            largura - margem - contador_largura - 28,
            120,
            largura - margem,
            148
        ),
        radius=14,
        fill=(20, 30, 65, 220),
        outline=(60, 140, 255, 180),
        width=1
    )

    draw.text(
        (
            largura - margem - contador_largura - 14,
            127
        ),
        contador,
        font=FONT_PEQUENA,
        fill=(180, 220, 255, 255)
    )

    # --------------------------------------------------------
    # SESSION
    # --------------------------------------------------------

    timeout = aiohttp.ClientTimeout(
        total=12
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        for indice, item in enumerate(itens):

            coluna = indice % colunas
            linha = indice // colunas

            x = (
                margem
                + coluna * (
                    card_largura + espaco
                )
            )

            y = (
                topo
                + linha * (
                    card_altura + espaco
                )
            )

            raridade = item.get(
                "rarity",
                "Item"
            )

            cor = cor_raridade(
                raridade
            )

            # ------------------------------------------------
            # GLOW DO CARD
            # ------------------------------------------------

            glow = Image.new(
                "RGBA",
                base.size,
                (0, 0, 0, 0)
            )

            glow_draw = ImageDraw.Draw(
                glow
            )

            glow_draw.rounded_rectangle(
                (
                    x - 5,
                    y - 5,
                    x + card_largura + 5,
                    y + card_altura + 5
                ),
                radius=18,
                outline=(
                    cor[0],
                    cor[1],
                    cor[2],
                    80
                ),
                width=8
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(12)
            )

            base.alpha_composite(
                glow
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
                radius=18,
                fill=(12, 15, 30, 245),
                outline=(
                    cor[0],
                    cor[1],
                    cor[2],
                    180
                ),
                width=2
            )

            # Barra de raridade
            draw.rounded_rectangle(
                (
                    x,
                    y,
                    x + card_largura,
                    y + 8
                ),
                radius=8,
                fill=(
                    cor[0],
                    cor[1],
                    cor[2],
                    255
                )
            )

            # ------------------------------------------------
            # IMAGEM
            # ------------------------------------------------

            area_x1 = x + 15
            area_y1 = y + 25
            area_x2 = x + card_largura - 15
            area_y2 = y + 250

            # Fundo da imagem
            draw.rounded_rectangle(
                (
                    area_x1,
                    area_y1,
                    area_x2,
                    area_y2
                ),
                radius=14,
                fill=(8, 11, 25, 255)
            )

            imagem_bytes = await baixar_imagem(
                session,
                item.get("image")
            )

            if imagem_bytes:

                try:
                    from io import BytesIO

                    item_img = Image.open(
                        BytesIO(imagem_bytes)
                    ).convert("RGBA")

                    item_img.thumbnail(
                        (
                            area_x2 - area_x1 - 20,
                            area_y2 - area_y1 - 20
                        ),
                        Image.Resampling.LANCZOS
                    )

                    # Glow atrás do item
                    centro_x = (
                        area_x1 + area_x2
                    ) // 2

                    centro_y = (
                        area_y1 + area_y2
                    ) // 2

                    adicionar_glow(
                        base,
                        (
                            centro_x,
                            centro_y
                        ),
                        raio=75,
                        intensidade=45
                    )

                    pos_x = (
                        centro_x
                        - item_img.width // 2
                    )

                    pos_y = (
                        centro_y
                        - item_img.height // 2
                    )

                    base.alpha_composite(
                        item_img,
                        (
                            pos_x,
                            pos_y
                        )
                    )

                except Exception as erro:
                    print(
                        f"[ITEM] Erro imagem: {erro}"
                    )

            # ------------------------------------------------
            # RARIDADE
            # ------------------------------------------------

            raridade_texto = (
                str(raridade).upper()
                if raridade
                else "ITEM"
            )

            raridade_texto = limitar_texto(
                raridade_texto,
                20
            )

            draw.rounded_rectangle(
                (
                    x + 15,
                    y + 265,
                    x + card_largura - 15,
                    y + 292
                ),
                radius=10,
                fill=(
                    cor[0],
                    cor[1],
                    cor[2],
                    35
                ),
                outline=(
                    cor[0],
                    cor[1],
                    cor[2],
                    130
                ),
                width=1
            )

            texto_centralizado(
                draw,
                (
                    x + 15,
                    y + 265,
                    x + card_largura - 15,
                    y + 292
                ),
                raridade_texto,
                FONT_RARIDADE,
                (
                    cor[0],
                    cor[1],
                    cor[2],
                    255
                )
            )

            # ------------------------------------------------
            # NOME
            # ------------------------------------------------

            nome = limitar_texto(
                item.get("name"),
                28
            )

            texto_centralizado(
                draw,
                (
                    x + 15,
                    y + 298,
                    x + card_largura - 15,
                    y + 330
                ),
                nome,
                FONT_NOME,
                (245, 248, 255, 255)
            )

            # ------------------------------------------------
            # PREÇO
            # ------------------------------------------------

            preco = item.get("price", 0)

            try:
                preco = int(preco)
            except Exception:
                preco = 0

            preco_texto = (
                f"{preco:,}".replace(",", ".")
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

            grupo_x = (
                x
                + (
                    card_largura
                    - grupo_largura
                ) // 2
            )

            grupo_y = y + 342

            desenhar_vbucks(
                draw,
                grupo_x + 10,
                grupo_y + 11,
                20
            )

            draw.text(
                (
                    grupo_x + 27,
                    grupo_y
                ),
                preco_texto,
                font=FONT_PRECO,
                fill=(110, 215, 255, 255)
            )

            # ------------------------------------------------
            # LIBERAÇÃO DE MEMÓRIA
            # ------------------------------------------------

            del imagem_bytes

            gc.collect()

    # --------------------------------------------------------
    # RODAPÉ
    # --------------------------------------------------------

    y_rodape = altura - 42

    draw.line(
        (
            margem,
            y_rodape - 10,
            largura - margem,
            y_rodape - 10
        ),
        fill=(50, 75, 130, 160),
        width=1
    )

    draw.text(
        (
            margem,
            y_rodape
        ),
        "VOIDHELPER",
        font=FONT_RODAPE,
        fill=(100, 190, 255, 255)
    )

    texto_direita = (
        "FORTNITE SHOP • ATUALIZAÇÃO AUTOMÁTICA"
    )

    bbox = draw.textbbox(
        (0, 0),
        texto_direita,
        font=FONT_PEQUENA
    )

    draw.text(
        (
            largura - margem - (
                bbox[2] - bbox[0]
            ),
            y_rodape + 2
        ),
        texto_direita,
        font=FONT_PEQUENA,
        fill=(110, 120, 155, 255)
    )

    # --------------------------------------------------------
    # SALVAR JPEG
    # --------------------------------------------------------

    arquivo = tempfile.NamedTemporaryFile(
        suffix=".jpg",
        delete=False
    )

    caminho = arquivo.name

    arquivo.close()

    base = base.convert("RGB")

    base.save(
        caminho,
        "JPEG",
        quality=72
    )

    del base
    gc.collect()

    return caminho


# ============================================================
# ESTADO DA LOJA
# ============================================================

def carregar_estado():
    if not os.path.exists(
        SHOP_STATE_FILE
    ):
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
        with open(
            SHOP_STATE_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                estado,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

    except Exception as erro:
        print(
            f"[STATE] Erro: {erro}"
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
# ATUALIZAR LOJA
# ============================================================

async def atualizar_loja():

    await bot.wait_until_ready()

    print(
        "[LOJA] Sistema de loja iniciado."
    )

    while not bot.is_closed():

        try:

            dados = await buscar_loja()

            if not dados:

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
                    "[LOJA] API não retornou hash."
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
            # MESMA LOJA
            # ------------------------------------------------

            if hash_anterior == shop_hash:

                print(
                    "[LOJA] Nenhuma atualização."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )

                continue

            print(
                "[LOJA] Nova atualização detectada!"
            )

            # ------------------------------------------------
            # EXTRAIR ITENS
            # ------------------------------------------------

            itens = extrair_itens_atualizacao(
                dados
            )

            print(
                f"[LOJA] {len(itens)} itens encontrados."
            )

            # ------------------------------------------------
            # CASO A EXTRAÇÃO FALHE
            # ------------------------------------------------

            if not itens:

                print(
                    "[LOJA] Nenhum item encontrado. "
                    "Não salvando o hash para tentar novamente."
                )

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )

                continue

            # ------------------------------------------------
            # GERAR IMAGEM
            # ------------------------------------------------

            caminho_imagem = (
                await gerar_imagem_loja(
                    itens,
                    data_loja
                )
            )

            if not caminho_imagem:

                print(
                    "[LOJA] Falha ao gerar imagem."
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
                        f"[LOJA] Erro canal: {erro}"
                    )

                    try:
                        os.remove(
                            caminho_imagem
                        )
                    except Exception:
                        pass

                    await asyncio.sleep(
                        INTERVALO_VERIFICACAO
                    )

                    continue

            # ------------------------------------------------
            # MENSAGEM EXISTENTE
            # ------------------------------------------------

            mensagem = None

            mensagem_id = estado.get(
                "message_id"
            )

            if mensagem_id:

                try:

                    mensagem = await canal.fetch_message(
                        int(mensagem_id)
                    )

                except Exception:

                    mensagem = None

            # ------------------------------------------------
            # ARQUIVO DISCORD
            # ------------------------------------------------

            arquivo = discord.File(
                caminho_imagem,
                filename="fortnite-shop.jpg"
            )

            texto = (
                "🎮 **FORTNITE ITEM SHOP**\n"
                "⚡ **Nova atualização da loja detectada!**\n\n"
                f"🛍️ **{len(itens)} itens atualizados**\n"
                "🤖 Atualização automática pelo VoidHelper"
            )

            try:

                if mensagem:

                    await mensagem.edit(
                        content=texto,
                        attachments=[arquivo]
                    )

                    print(
                        "[LOJA] Mensagem atualizada."
                    )

                else:

                    mensagem = await canal.send(
                        content=texto,
                        file=arquivo
                    )

                    print(
                        "[LOJA] Nova mensagem criada."
                    )

            except Exception as erro:

                print(
                    f"[LOJA] Erro Discord: {erro}"
                )

                try:
                    os.remove(
                        caminho_imagem
                    )
                except Exception:
                    pass

                await asyncio.sleep(
                    INTERVALO_VERIFICACAO
                )

                continue

            # ------------------------------------------------
            # SALVAR ESTADO
            # ------------------------------------------------

            novo_estado = {
                "shop_hash": shop_hash,
                "message_id": mensagem.id,
                "shop_date": data_loja,
                "items_count": len(itens),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            salvar_estado(
                novo_estado
            )

            # ------------------------------------------------
            # REMOVER ARQUIVO
            # ------------------------------------------------

            try:
                os.remove(
                    caminho_imagem
                )
            except Exception:
                pass

            gc.collect()

        except Exception as erro:

            print(
                f"[LOJA] Erro geral: {erro}"
            )

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
# TESTE DA LOJA
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    mensagem = await ctx.send(
        "🔄 Gerando a loja gamer..."
    )

    try:

        dados = await buscar_loja()

        if not dados:

            await mensagem.edit(
                content="❌ Não consegui acessar a API da Fortnite."
            )

            return

        data = dados.get(
            "data",
            {}
        )

        itens = extrair_itens_atualizacao(
            dados
        )

        if not itens:

            await mensagem.edit(
                content=(
                    "⚠️ A API respondeu, "
                    "mas nenhum item foi identificado "
                    "na atualização atual."
                )
            )

            return

        caminho = await gerar_imagem_loja(
            itens,
            data.get("date")
        )

        if not caminho:

            await mensagem.edit(
                content="❌ Erro ao gerar a imagem."
            )

            return

        arquivo = discord.File(
            caminho,
            filename="fortnite-shop.jpg"
        )

        await mensagem.edit(
            content=(
                "🎮 **Preview da nova interface "
                "da Fortnite Item Shop**\n"
                f"🔥 {len(itens)} itens encontrados."
            ),
            attachments=[arquivo]
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
                f"❌ Erro ao testar a loja:\n"
                f"`{erro}`"
            )
        )


# ============================================================
# ERRO DE PERMISSÃO DO TESTE
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
            "❌ Você precisa ser administrador para usar esse comando."
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
        f"🤖 Bot conectado como {bot.user}"
    )

    print(
        f"🆔 ID: {bot.user.id}"
    )

    print(
        "🎮 Sistema Fortnite Shop: ONLINE"
    )

    print(
        "🟢 Sistema de reações: ONLINE"
    )

    print(
        "======================================"
    )

    if not hasattr(
        bot,
        "loja_task"
    ) or bot.loja_task.done():

        bot.loja_task = asyncio.create_task(
            atualizar_loja()
        )


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi encontrada."
    )


bot.run(TOKEN)