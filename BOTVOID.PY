import os
import io
import json
import gc
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CANAL_REACOES_ID = 1556998399461691443
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"
IDIOMA = "pt-BR"

INTERVALO_VERIFICACAO = 300

SHOP_STATE_FILE = "shop_state.json"

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

# Segurança de memória
MAX_IMAGE_BYTES = 700_000
MAX_ITENS = 40

# Tamanho da imagem final
IMAGEM_LARGURA = 1200

# ============================================================
# CORES
# ============================================================

FUNDO = (8, 10, 22)
FUNDO_2 = (13, 16, 34)

BRANCO = (245, 248, 255)
CINZA = (160, 166, 185)
CINZA_ESCURO = (70, 75, 95)

AZUL = (63, 155, 255)
AZUL_CLARO = (83, 213, 255)

ROXO = (155, 82, 255)
ROXO_CLARO = (193, 111, 255)

ROSA = (255, 76, 180)

LARANJA = (255, 145, 45)
AMARELO = (255, 205, 72)

VERDE = (65, 215, 130)

# ============================================================
# FONTES
# ============================================================


def carregar_fonte(tamanho, negrito=False):
    caminhos = []

    if os.name == "nt":
        if negrito:
            caminhos.extend([
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
            ])
        else:
            caminhos.extend([
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ])
    else:
        if negrito:
            caminhos.extend([
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ])
        else:
            caminhos.extend([
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ])

    for caminho in caminhos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue

    return ImageFont.load_default()


FONTE_TITULO = carregar_fonte(48, True)
FONTE_SUBTITULO = carregar_fonte(20, True)
FONTE_SECAO = carregar_fonte(28, True)
FONTE_ITEM = carregar_fonte(20, True)
FONTE_CATEGORIA = carregar_fonte(14, True)
FONTE_PRECO = carregar_fonte(21, True)
FONTE_RARIDADE = carregar_fonte(12, True)
FONTE_PEQUENA = carregar_fonte(13, False)
FONTE_PEQUENA_NEGRITO = carregar_fonte(13, True)
FONTE_DATA = carregar_fonte(16, True)
FONTE_VOID = carregar_fonte(18, True)


# ============================================================
# RARIDADES
# ============================================================


def cor_raridade(raridade):
    if not raridade:
        return CINZA

    r = str(raridade).lower()

    if "lend" in r or "legend" in r:
        return LARANJA

    if "épico" in r or "epic" in r:
        return ROXO

    if "raro" in r or "rare" in r:
        return AZUL

    if "incomum" in r or "uncommon" in r:
        return VERDE

    if "mítico" in r or "mythic" in r:
        return AMARELO

    if "icon" in r:
        return AMARELO

    return CINZA


def nome_raridade(item):
    raridade = item.get("rarity")

    if isinstance(raridade, dict):
        return (
            raridade.get("displayValue")
            or raridade.get("displayName")
            or raridade.get("value")
            or "COMUM"
        )

    if isinstance(raridade, str):
        return raridade

    return "COMUM"


# ============================================================
# ESTADO DA LOJA
# ============================================================


def carregar_estado():
    try:
        if not os.path.exists(SHOP_STATE_FILE):
            return {}

        with open(SHOP_STATE_FILE, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)

    except Exception as erro:
        print(f"[AVISO] Não foi possível carregar estado: {erro}")
        return {}


def salvar_estado(estado):
    try:
        with open(SHOP_STATE_FILE, "w", encoding="utf-8") as arquivo:
            json.dump(
                estado,
                arquivo,
                ensure_ascii=False,
                indent=2
            )
    except Exception as erro:
        print(f"[ERRO] Não foi possível salvar estado: {erro}")


# ============================================================
# TEXTO
# ============================================================


def texto_seguro(texto):
    if texto is None:
        return ""

    return str(texto).strip()


def cortar_texto(texto, limite):
    texto = texto_seguro(texto)

    if len(texto) <= limite:
        return texto

    return texto[:limite - 3] + "..."


def centralizar_texto(draw, texto, y, fonte, largura, fill):
    caixa = draw.textbbox((0, 0), texto, font=fonte)
    largura_texto = caixa[2] - caixa[0]

    x = (largura - largura_texto) // 2

    draw.text(
        (x, y),
        texto,
        font=fonte,
        fill=fill
    )


# ============================================================
# API
# ============================================================


async def buscar_loja():
    timeout = aiohttp.ClientTimeout(total=25)

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
        ) as sessao:

            async with sessao.get(
                FORTNITE_SHOP_URL,
                params=params
            ) as resposta:

                if resposta.status != 200:
                    print(
                        f"[ERRO] Fortnite API respondeu HTTP {resposta.status}"
                    )
                    return None

                return await resposta.json()

    except asyncio.TimeoutError:
        print("[ERRO] Timeout ao consultar Fortnite API.")
        return None

    except Exception as erro:
        print(f"[ERRO] Falha na API: {erro}")
        return None


# ============================================================
# EXTRAÇÃO DOS ITENS
# ============================================================


def extrair_itens(dados):
    try:
        entries = dados.get("data", {}).get("entries", [])

        if not isinstance(entries, list):
            return []

    except Exception:
        return []

    agora = datetime.now(FUSO_BRASIL)

    resultado = []
    ids_processados = set()

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        # ----------------------------------------------------
        # Verifica validade temporal da oferta
        # ----------------------------------------------------

        in_date = entry.get("inDate")
        out_date = entry.get("outDate")

        try:
            if in_date:
                entrada = datetime.fromisoformat(
                    in_date.replace("Z", "+00:00")
                )

                if entrada.tzinfo is None:
                    entrada = entrada.replace(tzinfo=FUSO_BRASIL)

                if agora.astimezone(entrada.tzinfo) < entrada:
                    continue

        except Exception:
            pass

        try:
            if out_date:
                saida = datetime.fromisoformat(
                    out_date.replace("Z", "+00:00")
                )

                if saida.tzinfo is None:
                    saida = saida.replace(tzinfo=FUSO_BRASIL)

                if agora.astimezone(saida.tzinfo) > saida:
                    continue

        except Exception:
            pass

        itens_br = entry.get("brItems") or []

        if not itens_br:
            itens_br = entry.get("items") or []

        if not isinstance(itens_br, list):
            continue

        for item in itens_br:

            if not isinstance(item, dict):
                continue

            item_id = (
                item.get("id")
                or item.get("offerId")
                or entry.get("offerId")
            )

            if not item_id:
                continue

            if item_id in ids_processados:
                continue

            ids_processados.add(item_id)

            # ------------------------------------------------
            # Nome
            # ------------------------------------------------

            nome = (
                item.get("name")
                or item.get("displayName")
                or "Item desconhecido"
            )

            # ------------------------------------------------
            # Categoria
            # ------------------------------------------------

            tipo = item.get("type")

            if isinstance(tipo, dict):
                categoria = (
                    tipo.get("displayValue")
                    or tipo.get("displayName")
                    or tipo.get("value")
                    or "ITEM"
                )
            else:
                categoria = tipo or "ITEM"

            # ------------------------------------------------
            # Raridade
            # ------------------------------------------------

            raridade = nome_raridade(item)

            # ------------------------------------------------
            # Imagem
            # ------------------------------------------------

            imagens = item.get("images") or {}

            imagem_url = (
                imagens.get("featured")
                or imagens.get("icon")
                or imagens.get("smallIcon")
                or imagens.get("small")
            )

            if not imagem_url:
                continue

            # ------------------------------------------------
            # Preço
            # ------------------------------------------------

            preco = (
                entry.get("finalPrice")
                or entry.get("regularPrice")
                or item.get("finalPrice")
                or item.get("regularPrice")
                or 0
            )

            resultado.append({
                "id": str(item_id),
                "name": texto_seguro(nome),
                "category": texto_seguro(categoria),
                "rarity": texto_seguro(raridade),
                "price": preco,
                "image": imagem_url,
            })

            if len(resultado) >= MAX_ITENS:
                return resultado

    return resultado


# ============================================================
# DOWNLOAD DE IMAGEM
# ============================================================


async def baixar_imagem(sessao, url):
    if not url:
        return None

    try:
        async with sessao.get(url) as resposta:

            if resposta.status != 200:
                return None

            content_length = resposta.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > MAX_IMAGE_BYTES:
                        return None
                except Exception:
                    pass

            dados = await resposta.read()

            if len(dados) > MAX_IMAGE_BYTES:
                return None

            imagem = Image.open(io.BytesIO(dados))

            # Converte para RGBA apenas localmente.
            if imagem.mode not in ("RGB", "RGBA"):
                imagem = imagem.convert("RGBA")

            imagem.thumbnail(
                (250, 210),
                Image.Resampling.LANCZOS
            )

            return imagem

    except Exception as erro:
        print(f"[AVISO] Erro ao baixar imagem: {erro}")
        return None


# ============================================================
# FUNDO
# ============================================================


def criar_fundo(largura, altura):
    imagem = Image.new(
        "RGB",
        (largura, altura),
        FUNDO
    )

    draw = ImageDraw.Draw(imagem)

    # Fundo em faixas horizontais
    passo = 70

    for y in range(0, altura, passo):
        if (y // passo) % 2 == 0:
            draw.rectangle(
                (0, y, largura, y + passo),
                fill=FUNDO_2
            )

    # Linhas diagonais leves
    for x in range(-altura, largura, 160):
        draw.line(
            (x, 0, x + altura, altura),
            fill=(20, 24, 48),
            width=2
        )

    # Linha superior
    draw.rectangle(
        (0, 0, largura, 5),
        fill=ROXO
    )

    draw.rectangle(
        (largura // 2, 0, largura, 5),
        fill=AZUL_CLARO
    )

    # Pequenos pontos decorativos
    pontos = [
        (80, 110),
        (240, 180),
        (440, 100),
        (680, 160),
        (900, 90),
        (1100, 180),
        (1020, 460),
        (130, 700),
        (760, 620),
        (1080, 800),
    ]

    for x, y in pontos:
        if y < altura:
            draw.ellipse(
                (x, y, x + 3, y + 3),
                fill=(80, 90, 150)
            )

    return imagem


# ============================================================
# CABEÇALHO
# ============================================================


def desenhar_cabecalho(imagem, draw, altura):
    largura = imagem.width

    # Área do header
    draw.rounded_rectangle(
        (30, 30, largura - 30, 190),
        radius=24,
        fill=(14, 17, 38),
        outline=(40, 46, 78),
        width=2
    )

    # Faixa decorativa
    draw.rounded_rectangle(
        (30, 30, 420, 36),
        radius=3,
        fill=ROXO
    )

    draw.rounded_rectangle(
        (420, 30, 680, 36),
        radius=3,
        fill=AZUL
    )

    draw.rounded_rectangle(
        (680, 30, 850, 36),
        radius=3,
        fill=ROSA
    )

    # --------------------------------------------------------
    # Título
    # --------------------------------------------------------

    draw.text(
        (60, 55),
        "FORTNITE",
        font=FONTE_TITULO,
        fill=BRANCO
    )

    draw.text(
        (63, 108),
        "ITEM SHOP",
        font=FONTE_SUBTITULO,
        fill=AZUL_CLARO
    )

    draw.text(
        (63, 137),
        "OS MELHORES ITENS, SEMPRE!",
        font=FONTE_PEQUENA_NEGRITO,
        fill=(170, 176, 205)
    )

    # --------------------------------------------------------
    # Painel de atualização
    # --------------------------------------------------------

    painel_x = 700
    painel_y = 52
    painel_w = 220
    painel_h = 105

    draw.rounded_rectangle(
        (
            painel_x,
            painel_y,
            painel_x + painel_w,
            painel_y + painel_h
        ),
        radius=16,
        fill=(20, 24, 48),
        outline=(52, 61, 100),
        width=2
    )

    draw.text(
        (painel_x + 18, painel_y + 12),
        "LOJA ATUALIZADA EM",
        font=FONTE_PEQUENA_NEGRITO,
        fill=(135, 145, 180)
    )

    agora = datetime.now(FUSO_BRASIL)

    data = agora.strftime("%d/%m/%Y")
    horario = agora.strftime("%H:%M")

    draw.text(
        (painel_x + 18, painel_y + 36),
        data,
        font=FONTE_DATA,
        fill=BRANCO
    )

    draw.text(
        (painel_x + 18, painel_y + 62),
        f"{horario} BRT",
        font=FONTE_PEQUENA_NEGRITO,
        fill=AZUL_CLARO
    )

    # --------------------------------------------------------
    # Painel V-Bucks
    # --------------------------------------------------------

    vb_x = 945
    vb_y = 52

    draw.rounded_rectangle(
        (vb_x, vb_y, largura - 60, vb_y + 105),
        radius=16,
        fill=(20, 24, 48),
        outline=(52, 61, 100),
        width=2
    )

    # Ícone V-Bucks estilizado
    cx = vb_x + 38
    cy = vb_y + 52

    draw.ellipse(
        (cx - 20, cy - 20, cx + 20, cy + 20),
        fill=(82, 202, 255),
        outline=(170, 240, 255),
        width=2
    )

    draw.text(
        (cx - 7, cy - 13),
        "V",
        font=FONTE_ITEM,
        fill=(10, 35, 60)
    )

    draw.text(
        (vb_x + 68, vb_y + 20),
        "V-BUCKS",
        font=FONTE_PEQUENA_NEGRITO,
        fill=AZUL_CLARO
    )

    draw.text(
        (vb_x + 68, vb_y + 45),
        "USE SEUS V-BUCKS",
        font=FONTE_PEQUENA_NEGRITO,
        fill=BRANCO
    )

    draw.text(
        (vb_x + 68, vb_y + 67),
        "PARA GARANTIR SEUS ITENS",
        font=carregar_fonte(10, False),
        fill=(135, 145, 180)
    )


# ============================================================
# NAVEGAÇÃO
# ============================================================


def desenhar_navegacao(draw, y):
    largura = IMAGEM_LARGURA

    abas = [
        ("★", "DESTAQUES"),
        ("◈", "DIÁRIO"),
        ("◆", "SKINS"),
        ("⚒", "PICARETAS"),
        ("◇", "ASA-DELTA"),
        ("●", "GESTOS"),
        ("♪", "MÚSICAS"),
    ]

    x = 35

    for indice, (icone, nome) in enumerate(abas):

        largura_aba = 150

        if indice == 0:
            fill = (79, 45, 150)
            outline = ROXO_CLARO
        else:
            fill = (17, 21, 42)
            outline = (42, 48, 75)

        draw.rounded_rectangle(
            (x, y, x + largura_aba, y + 42),
            radius=12,
            fill=fill,
            outline=outline,
            width=1
        )

        draw.text(
            (x + 12, y + 11),
            icone,
            font=FONTE_PEQUENA_NEGRITO,
            fill=BRANCO
        )

        draw.text(
            (x + 34, y + 12),
            nome,
            font=carregar_fonte(11, True),
            fill=BRANCO
        )

        x += largura_aba + 8

        if x > largura - 170:
            break


# ============================================================
# CARD DE ITEM
# ============================================================


def desenhar_card(
    imagem,
    draw,
    item,
    x,
    y,
    largura,
    altura,
    imagem_item
):
    raridade = item.get("rarity", "COMUM")
    cor = cor_raridade(raridade)

    # --------------------------------------------------------
    # Card
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (x, y, x + largura, y + altura),
        radius=18,
        fill=(16, 19, 38),
        outline=(42, 48, 76),
        width=2
    )

    # Linha de raridade
    draw.rounded_rectangle(
        (x + 1, y + 1, x + largura - 1, y + 10),
        radius=6,
        fill=cor
    )

    # --------------------------------------------------------
    # Label raridade
    # --------------------------------------------------------

    label = raridade.upper()

    draw.rounded_rectangle(
        (x + 12, y + 18, x + 105, y + 42),
        radius=8,
        fill=cor
    )

    draw.text(
        (x + 19, y + 24),
        label,
        font=FONTE_RARIDADE,
        fill=(10, 12, 20)
    )

    # --------------------------------------------------------
    # Área da imagem
    # --------------------------------------------------------

    area_top = y + 48
    area_bottom = y + altura - 92

    area_x1 = x + 10
    area_x2 = x + largura - 10

    draw.rounded_rectangle(
        (
            area_x1,
            area_top,
            area_x2,
            area_bottom
        ),
        radius=13,
        fill=(10, 13, 28)
    )

    # Pequeno brilho superior
    draw.line(
        (
            area_x1 + 12,
            area_top + 2,
            area_x2 - 12,
            area_top + 2
        ),
        fill=cor,
        width=2
    )

    # --------------------------------------------------------
    # Imagem do item
    # --------------------------------------------------------

    if imagem_item is not None:

        try:
            img = imagem_item.copy()

            max_w = int(largura * 0.82)
            max_h = int((area_bottom - area_top) * 0.82)

            img.thumbnail(
                (max_w, max_h),
                Image.Resampling.LANCZOS
            )

            iw, ih = img.size

            pos_x = x + (largura - iw) // 2
            pos_y = area_top + (
                (area_bottom - area_top - ih) // 2
            )

            if img.mode == "RGBA":
                imagem.paste(
                    img,
                    (pos_x, pos_y),
                    img
                )
            else:
                imagem.paste(
                    img,
                    (pos_x, pos_y)
                )

            del img

        except Exception as erro:
            print(f"[AVISO] Erro renderizando item: {erro}")

    # --------------------------------------------------------
    # Nome
    # --------------------------------------------------------

    nome = cortar_texto(
        item.get("name", "Item"),
        24
    )

    categoria = cortar_texto(
        item.get("category", "ITEM"),
        20
    )

    nome_fonte = FONTE_ITEM

    caixa = draw.textbbox(
        (0, 0),
        nome,
        font=nome_fonte
    )

    nome_largura = caixa[2] - caixa[0]

    if nome_largura > largura - 24:
        nome_fonte = carregar_fonte(17, True)

    draw.text(
        (x + 12, y + altura - 78),
        nome,
        font=nome_fonte,
        fill=BRANCO
    )

    # Categoria
    draw.text(
        (x + 12, y + altura - 51),
        categoria.upper(),
        font=FONTE_CATEGORIA,
        fill=(125, 132, 160)
    )

    # --------------------------------------------------------
    # Preço
    # --------------------------------------------------------

    preco = item.get("price", 0)

    try:
        preco_texto = f"{int(preco):,}".replace(",", ".")
    except Exception:
        preco_texto = str(preco)

    # moeda V-Bucks
    moeda_x = x + largura - 55
    moeda_y = y + altura - 59

    draw.ellipse(
        (
            moeda_x,
            moeda_y,
            moeda_x + 27,
            moeda_y + 27
        ),
        fill=(82, 202, 255),
        outline=(170, 240, 255),
        width=1
    )

    draw.text(
        (moeda_x + 8, moeda_y + 5),
        "V",
        font=carregar_fonte(12, True),
        fill=(8, 35, 58)
    )

    draw.text(
        (
            moeda_x - 65,
            moeda_y + 2
        ),
        preco_texto,
        font=FONTE_PRECO,
        fill=BRANCO
    )


# ============================================================
# GERAR IMAGEM
# ============================================================


async def gerar_imagem_loja(itens):
    if not itens:
        print("[AVISO] Nenhum item para gerar.")
        return None

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------

    margem = 30
    espacamento = 18

    colunas = 4

    largura_card = (
        IMAGEM_LARGURA
        - (margem * 2)
        - (espacamento * (colunas - 1))
    ) // colunas

    altura_card = 330

    header_altura = 190
    nav_y = 205
    nav_altura = 42

    secao_y = 265

    inicio_cards = 315

    linhas = (
        (len(itens) + colunas - 1)
        // colunas
    )

    # Footer
    footer_altura = 150

    altura_total = (
        inicio_cards
        + (linhas * altura_card)
        + ((linhas - 1) * espacamento)
        + footer_altura
        + 30
    )

    # --------------------------------------------------------
    # Cria imagem
    # --------------------------------------------------------

    imagem = criar_fundo(
        IMAGEM_LARGURA,
        altura_total
    )

    draw = ImageDraw.Draw(imagem)

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    desenhar_cabecalho(
        imagem,
        draw,
        altura_total
    )

    # --------------------------------------------------------
    # Navegação
    # --------------------------------------------------------

    desenhar_navegacao(
        draw,
        nav_y
    )

    # --------------------------------------------------------
    # Seção
    # --------------------------------------------------------

    draw.text(
        (35, secao_y),
        "★ DESTAQUES",
        font=FONTE_SECAO,
        fill=BRANCO
    )

    draw.text(
        (760, secao_y + 8),
        "ITENS DA LOJA HOJE",
        font=FONTE_PEQUENA_NEGRITO,
        fill=(120, 130, 165)
    )

    draw.line(
        (35, secao_y + 43, IMAGEM_LARGURA - 35, secao_y + 43),
        fill=(45, 50, 78),
        width=1
    )

    # --------------------------------------------------------
    # Sessão HTTP única
    # --------------------------------------------------------

    timeout = aiohttp.ClientTimeout(total=20)

    headers = {
        "User-Agent": "VoidHelper/1.0"
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers
    ) as sessao:

        for indice, item in enumerate(itens):

            linha = indice // colunas
            coluna = indice % colunas

            x = (
                margem
                + coluna * (largura_card + espacamento)
            )

            y = (
                inicio_cards
                + linha * (altura_card + espacamento)
            )

            imagem_item = None

            try:
                imagem_item = await baixar_imagem(
                    sessao,
                    item.get("image")
                )

                desenhar_card(
                    imagem,
                    draw,
                    item,
                    x,
                    y,
                    largura_card,
                    altura_card,
                    imagem_item
                )

            except Exception as erro:
                print(
                    f"[AVISO] Erro processando item "
                    f"{item.get('name')}: {erro}"
                )

            finally:
                if imagem_item is not None:
                    try:
                        imagem_item.close()
                    except Exception:
                        pass

                    del imagem_item

                gc.collect()

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    footer_y = inicio_cards + (
        linhas * altura_card
    ) + (
        (linhas - 1) * espacamento
    ) + 25

    footer_bottom = altura_total - 25

    draw.rounded_rectangle(
        (
            30,
            footer_y,
            IMAGEM_LARGURA - 30,
            footer_bottom
        ),
        radius=20,
        fill=(14, 17, 37),
        outline=(45, 50, 80),
        width=2
    )

    # Discord
    draw.ellipse(
        (
            55,
            footer_y + 32,
            105,
            footer_y + 82
        ),
        fill=(88, 101, 242)
    )

    draw.text(
        (70, footer_y + 43),
        "D",
        font=carregar_fonte(22, True),
        fill=BRANCO
    )

    draw.text(
        (125, footer_y + 25),
        "FIQUE POR DENTRO!",
        font=FONTE_VOID,
        fill=BRANCO
    )

    draw.text(
        (125, footer_y + 52),
        "Entre no nosso servidor do Discord",
        font=FONTE_PEQUENA,
        fill=(150, 158, 185)
    )

    draw.text(
        (125, footer_y + 74),
        "e receba novidades em primeira mão!",
        font=FONTE_PEQUENA,
        fill=(150, 158, 185)
    )

    # Código
    central_x = 600

    draw.text(
        (central_x, footer_y + 25),
        "USE O CÓDIGO",
        font=FONTE_PEQUENA_NEGRITO,
        fill=ROXO_CLARO,
        anchor="mm"
    )

    draw.text(
        (central_x, footer_y + 53),
        "VOIDHELPER",
        font=carregar_fonte(25, True),
        fill=BRANCO,
        anchor="mm"
    )

    # Slogan
    draw.text(
        (965, footer_y + 30),
        "Mais itens.",
        font=FONTE_VOID,
        fill=AZUL_CLARO,
        anchor="mm"
    )

    draw.text(
        (965, footer_y + 58),
        "Mais diversão.",
        font=FONTE_VOID,
        fill=ROXO_CLARO,
        anchor="mm"
    )

    draw.text(
        (965, footer_y + 83),
        "VOIDHELPER",
        font=FONTE_PEQUENA_NEGRITO,
        fill=(110, 118, 150),
        anchor="mm"
    )

    # --------------------------------------------------------
    # Salvar em memória
    # --------------------------------------------------------

    buffer = io.BytesIO()

    imagem.save(
        buffer,
        format="JPEG",
        quality=67,
        optimize=True,
        progressive=True
    )

    imagem.close()

    buffer.seek(0)

    tamanho = len(buffer.getvalue())

    print(
        f"[IMAGEM] Gerada: "
        f"{tamanho / 1024:.1f} KB"
    )

    # --------------------------------------------------------
    # Segurança de memória/arquivo
    # --------------------------------------------------------

    if tamanho > MAX_IMAGE_BYTES:
        print(
            "[AVISO] Imagem ultrapassou o limite. "
            "Tentando compressão adicional."
        )

        buffer.seek(0)

        imagem_temp = Image.open(buffer)

        novo_buffer = io.BytesIO()

        imagem_temp.save(
            novo_buffer,
            format="JPEG",
            quality=52,
            optimize=True,
            progressive=True
        )

        imagem_temp.close()

        buffer.close()

        buffer = novo_buffer
        buffer.seek(0)

        print(
            f"[IMAGEM] Após compressão: "
            f"{len(buffer.getvalue()) / 1024:.1f} KB"
        )

    gc.collect()

    return buffer


# ============================================================
# ATUALIZAR MENSAGEM DA LOJA
# ============================================================


async def atualizar_loja(forcar=False):
    print("[LOJA] Verificando loja Fortnite...")

    dados = await buscar_loja()

    if not dados:
        return

    try:
        data = dados.get("data", {})
        shop_hash = data.get("hash")

    except Exception:
        print("[ERRO] Resposta inválida da API.")
        return

    if not shop_hash:
        print("[ERRO] Hash da loja não encontrado.")
        return

    estado = carregar_estado()

    hash_anterior = estado.get("shop_hash")

    if not forcar and hash_anterior == shop_hash:
        print("[LOJA] Nenhuma alteração detectada.")
        return

    print("[LOJA] Nova loja detectada.")

    itens = extrair_itens(dados)

    if not itens:
        print("[LOJA] Nenhum item encontrado.")
        return

    print(
        f"[LOJA] {len(itens)} itens encontrados."
    )

    imagem_buffer = await gerar_imagem_loja(itens)

    if not imagem_buffer:
        print("[ERRO] Não foi possível gerar imagem.")
        return

    try:
        canal = bot.get_channel(CANAL_LOJA_ID)

        if canal is None:
            canal = await bot.fetch_channel(
                CANAL_LOJA_ID
            )

        if canal is None:
            print("[ERRO] Canal da loja não encontrado.")
            return

        # ----------------------------------------------------
        # Recupera mensagem existente
        # ----------------------------------------------------

        message_id = estado.get("message_id")

        mensagem = None

        if message_id:
            try:
                mensagem = await canal.fetch_message(
                    int(message_id)
                )

            except discord.NotFound:
                mensagem = None

            except discord.HTTPException as erro:
                print(
                    f"[AVISO] Não foi possível buscar mensagem: {erro}"
                )

        arquivo = discord.File(
            imagem_buffer,
            filename="voidhelper_loja.jpg"
        )

        conteudo = (
            "## 🛒 **FORTNITE ITEM SHOP**\n"
            "### ✨ Loja atualizada\n"
            f"**{len(itens)} itens disponíveis** • "
            "Atualização automática\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💜 **VOIDHELPER** • Loja Fortnite"
        )

        # ----------------------------------------------------
        # Editar mensagem existente
        # ----------------------------------------------------

        if mensagem:

            try:
                await mensagem.edit(
                    content=conteudo,
                    attachments=[arquivo]
                )

                print(
                    f"[LOJA] Mensagem {mensagem.id} atualizada."
                )

            except discord.HTTPException as erro:
                print(
                    f"[ERRO] Falha ao editar mensagem: {erro}"
                )

                return

        # ----------------------------------------------------
        # Criar mensagem nova
        # ----------------------------------------------------

        else:

            try:
                mensagem = await canal.send(
                    content=conteudo,
                    file=arquivo
                )

                print(
                    f"[LOJA] Nova mensagem criada: {mensagem.id}"
                )

                estado["message_id"] = mensagem.id

            except discord.HTTPException as erro:
                print(
                    f"[ERRO] Falha ao criar mensagem: {erro}"
                )

                return

        # ----------------------------------------------------
        # Salvar hash
        # ----------------------------------------------------

        estado["shop_hash"] = shop_hash
        estado["updated_at"] = datetime.now(
            FUSO_BRASIL
        ).isoformat()

        estado["items_count"] = len(itens)

        salvar_estado(estado)

    finally:
        try:
            imagem_buffer.close()
        except Exception:
            pass

        del imagem_buffer

        gc.collect()

        print("[MEMÓRIA] Limpeza concluída.")


# ============================================================
# BOT
# ============================================================


intents = discord.Intents.default()

intents.message_content = True
intents.messages = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# EVENTO DE MENSAGEM
# ============================================================


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # --------------------------------------------------------
    # Sistema de reações
    # --------------------------------------------------------

    if message.channel.id == CANAL_REACOES_ID:

        try:
            await message.add_reaction("🟢")
            await message.add_reaction("⚖️")
            await message.add_reaction("🔴")

        except discord.HTTPException as erro:
            print(
                f"[REAÇÕES] Erro ao reagir: {erro}"
            )

    await bot.process_commands(message)


# ============================================================
# COMANDO DE TESTE
# ============================================================


@bot.command(name="testeloja")
@commands.has_permissions(administrator=True)
async def teste_loja(ctx):

    mensagem = await ctx.send(
        "⏳ **Gerando preview da nova loja...**"
    )

    try:

        await atualizar_loja(forcar=True)

        await mensagem.edit(
            content=(
                "✅ **Preview da loja gerado!**\n"
                "A mensagem da loja foi atualizada."
            )
        )

    except Exception as erro:

        print(
            f"[TESTE] Erro: {erro}"
        )

        await mensagem.edit(
            content=(
                "❌ **Erro ao gerar a loja.**\n"
                f"`{erro}`"
            )
        )


@teste_loja.error
async def teste_loja_error(ctx, erro):

    if isinstance(
        erro,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ Você precisa ser administrador para usar esse comando.",
            delete_after=8
        )


# ============================================================
# TAREFA AUTOMÁTICA
# ============================================================


@tasks.loop(seconds=INTERVALO_VERIFICACAO)
async def verificar_loja():

    try:
        await atualizar_loja()

    except Exception as erro:

        print(
            f"[LOOP] Erro inesperado: {erro}"
        )

        gc.collect()


@verificar_loja.before_loop
async def antes_verificar_loja():

    await bot.wait_until_ready()

    print(
        "[LOJA] Sistema automático iniciado."
    )


# ============================================================
# READY
# ============================================================


@bot.event
async def on_ready():

    print("=" * 60)

    print(
        f"[BOT] Logado como "
        f"{bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        f"[BOT] Servidores: "
        f"{len(bot.guilds)}"
    )

    print(
        "[BOT] VoidHelper online."
    )

    print("=" * 60)

    if not verificar_loja.is_running():

        verificar_loja.start()

        print(
            "[LOJA] Loop de verificação iniciado."
        )


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================


@bot.event
async def on_command_error(ctx, erro):

    if isinstance(
        erro,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        erro,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ Você não possui permissão para usar esse comando.",
            delete_after=8
        )
        return

    print(
        f"[COMANDO] Erro: {erro}"
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================


if not TOKEN:

    raise RuntimeError(
        "A variável de ambiente DISCORD_TOKEN não foi encontrada."
    )


print("[SISTEMA] Iniciando VoidHelper...")

bot.run(TOKEN)