import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import gc
import os
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageFile


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CANAL_REACOES_ID = 1556998399461691443
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"
IDIOMA = "pt-BR"

# Verifica a API a cada 5 minutos
INTERVALO_VERIFICACAO = 300

# Arquivo para lembrar a mensagem da loja
SHOP_STATE_FILE = "shop_state.json"

# Fuso horário do Brasil
FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


# ============================================================
# CONFIGURAÇÃO DA IMAGEM
# ============================================================

LARGURA_FINAL = 1200

COLUNAS = 4

MARGEM_LATERAL = 28
MARGEM_TOPO = 115

ESPACO_HORIZONTAL = 12
ESPACO_VERTICAL = 14

# A largura é calculada automaticamente
CARD_LARGURA = (
    LARGURA_FINAL
    - (MARGEM_LATERAL * 2)
    - (ESPACO_HORIZONTAL * (COLUNAS - 1))
) // COLUNAS

CARD_ALTURA = 215

IMAGEM_LARGURA = CARD_LARGURA - 20
IMAGEM_ALTURA = 140

QUALIDADE_JPEG = 60

MAX_IMAGEM_DOWNLOAD = 1 * 1024 * 1024

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Evita imagens absurdamente grandes
Image.MAX_IMAGE_PIXELS = 10_000_000


# ============================================================
# CORES
# ============================================================

COR_FUNDO = (9, 11, 18)
COR_FUNDO_2 = (14, 17, 27)

COR_CARD = (20, 23, 35)
COR_CARD_BORDA = (48, 54, 75)

COR_AREA_IMAGEM = (11, 14, 22)

COR_TITULO = (255, 255, 255)
COR_SUBTITULO = (160, 166, 180)

COR_PRECO = (255, 213, 74)
COR_ACCENT = (65, 125, 255)

COR_BRANCO = (255, 255, 255)


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(tamanho):
    caminhos = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for caminho in caminhos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            pass

    return ImageFont.load_default()


FONTE_TITULO = carregar_fonte(32)
FONTE_SUBTITULO = carregar_fonte(17)
FONTE_NOME = carregar_fonte(16)
FONTE_PRECO = carregar_fonte(16)
FONTE_TIPO = carregar_fonte(13)


# ============================================================
# UTILIDADES
# ============================================================

def cortar_texto(draw, texto, fonte, largura_max):
    """
    Corta o texto para caber dentro do card.
    """

    texto = str(texto or "Sem nome")

    if draw.textbbox((0, 0), texto, font=fonte)[2] <= largura_max:
        return texto

    while len(texto) > 3:
        texto = texto[:-1]

        teste = texto + "..."

        if draw.textbbox((0, 0), teste, font=fonte)[2] <= largura_max:
            return teste

    return "..."


def obter_data_brasil():
    return datetime.now(FUSO_BRASIL).date()


def converter_data(data):
    """
    Converte datas da API para datetime.

    Aceita:
    2026-10-07T00:00:00Z
    2026-10-07T00:00:00.000Z
    etc.
    """

    if not data:
        return None

    if isinstance(data, datetime):
        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)

        return data.astimezone(FUSO_BRASIL)

    if not isinstance(data, str):
        return None

    try:
        texto = data.strip()

        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"

        dt = datetime.fromisoformat(texto)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(FUSO_BRASIL)

    except Exception:
        return None


def pegar_primeiro(dicionario, *chaves):
    """
    Retorna a primeira chave existente.
    """

    if not isinstance(dicionario, dict):
        return None

    for chave in chaves:
        valor = dicionario.get(chave)

        if valor is not None:
            return valor

    return None


def obter_imagem_cosmetico(item):
    """
    Procura uma imagem válida do item.
    """

    if not isinstance(item, dict):
        return None

    imagens = item.get("images")

    if isinstance(imagens, dict):

        # Prioridade para imagens maiores
        for chave in [
            "featured",
            "icon",
            "png",
            "full_background",
            "fullBackground",
            "background",
        ]:
            url = imagens.get(chave)

            if isinstance(url, str) and url.startswith("http"):
                return url

    # Algumas estruturas podem possuir image diretamente
    for chave in [
        "image",
        "icon",
        "featured",
        "iconUrl",
        "imageUrl",
    ]:
        url = item.get(chave)

        if isinstance(url, str) and url.startswith("http"):
            return url

    return None


def obter_nome_cosmetico(item):
    if not isinstance(item, dict):
        return "Item Fortnite"

    return (
        item.get("name")
        or item.get("displayName")
        or item.get("title")
        or "Item Fortnite"
    )


def obter_tipo_cosmetico(item):
    if not isinstance(item, dict):
        return "Item"

    tipo = item.get("type")

    if isinstance(tipo, dict):
        tipo = tipo.get("displayValue") or tipo.get("value")

    if tipo:
        return str(tipo)

    return "Item"


def obter_preco(entry):
    if not isinstance(entry, dict):
        return 0

    valor = pegar_primeiro(
        entry,
        "finalPrice",
        "final_price",
        "regularPrice",
        "regular_price",
    )

    if valor is None:
        return 0

    try:
        return int(valor)
    except Exception:
        return 0


# ============================================================
# EXTRAÇÃO DE ITENS
# ============================================================

def extrair_cosmeticos_da_entry(entry):
    """
    Uma entrada da loja pode conter diferentes estruturas.

    Esta função tenta encontrar todos os cosméticos
    relacionados àquela oferta.
    """

    encontrados = []

    if not isinstance(entry, dict):
        return encontrados

    # --------------------------------------------------------
    # BR
    # --------------------------------------------------------

    br = entry.get("br")

    if isinstance(br, dict):
        encontrados.append(br)

    elif isinstance(br, list):
        encontrados.extend(
            item for item in br
            if isinstance(item, dict)
        )

    # --------------------------------------------------------
    # Tracks
    # --------------------------------------------------------

    tracks = entry.get("tracks")

    if isinstance(tracks, list):
        encontrados.extend(
            item for item in tracks
            if isinstance(item, dict)
        )

    # --------------------------------------------------------
    # Instruments
    # --------------------------------------------------------

    instruments = entry.get("instruments")

    if isinstance(instruments, list):
        encontrados.extend(
            item for item in instruments
            if isinstance(item, dict)
        )

    # --------------------------------------------------------
    # Cars
    # --------------------------------------------------------

    cars = entry.get("cars")

    if isinstance(cars, list):
        encontrados.extend(
            item for item in cars
            if isinstance(item, dict)
        )

    # --------------------------------------------------------
    # LEGO
    # --------------------------------------------------------

    lego = entry.get("legoKits")

    if isinstance(lego, list):
        encontrados.extend(
            item for item in lego
            if isinstance(item, dict)
        )

    # --------------------------------------------------------
    # Estruturas alternativas
    # --------------------------------------------------------

    for chave in [
        "items",
        "item",
        "granted",
        "grants",
        "cosmetics",
    ]:

        valor = entry.get(chave)

        if isinstance(valor, dict):
            encontrados.append(valor)

        elif isinstance(valor, list):
            encontrados.extend(
                item for item in valor
                if isinstance(item, dict)
            )

    # --------------------------------------------------------
    # Se a própria entry for um cosmético
    # --------------------------------------------------------

    if (
        not encontrados
        and (
            "name" in entry
            or "displayName" in entry
        )
    ):
        encontrados.append(entry)

    return encontrados


def extrair_itens_do_dia(shop_data):
    """
    Retorna somente as ofertas que possuem IN_DATE
    correspondente ao dia atual no Brasil.

    IMPORTANTE:
    Não pegamos simplesmente todos os itens da loja.
    """

    hoje = obter_data_brasil()

    entries = shop_data.get("entries", [])

    if not isinstance(entries, list):
        print("[LOJA] A API não retornou entries como lista.")
        return []

    print(f"[LOJA] Total de ofertas recebidas: {len(entries)}")
    print(f"[LOJA] Data considerada no Brasil: {hoje}")

    itens = []

    vistos = set()

    for numero, entry in enumerate(entries, start=1):

        if not isinstance(entry, dict):
            continue

        # ----------------------------------------------------
        # DATA DE ENTRADA
        # ----------------------------------------------------

        in_date = pegar_primeiro(
            entry,
            "inDate",
            "in_date",
        )

        data_entrada = converter_data(in_date)

        if data_entrada is None:
            print(
                f"[LOJA] Oferta {numero}: "
                f"sem inDate válido."
            )
            continue

        # ----------------------------------------------------
        # FILTRO PRINCIPAL
        # ----------------------------------------------------

        if data_entrada.date() != hoje:
            continue

        print(
            f"[LOJA] Oferta {numero} entrou hoje: "
            f"{data_entrada.isoformat()}"
        )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        preco = obter_preco(entry)

        # ----------------------------------------------------
        # COSMÉTICOS
        # ----------------------------------------------------

        cosmeticos = extrair_cosmeticos_da_entry(entry)

        # Caso não tenha cosmético interno, tenta usar
        # informações da própria entry.
        if not cosmeticos:
            cosmeticos = [entry]

        for item in cosmeticos:

            if not isinstance(item, dict):
                continue

            nome = obter_nome_cosmetico(item)
            imagem = obter_imagem_cosmetico(item)
            tipo = obter_tipo_cosmetico(item)

            # Identificador para evitar duplicações
            item_id = (
                item.get("id")
                or item.get("offerId")
                or item.get("offer_id")
                or f"{nome}-{imagem}"
            )

            if item_id in vistos:
                continue

            vistos.add(item_id)

            itens.append({
                "id": str(item_id),
                "name": nome,
                "image": imagem,
                "type": tipo,
                "price": preco,
                "in_date": data_entrada.isoformat(),
            })

    print(
        f"[LOJA] ITENS NOVOS DE HOJE: {len(itens)}"
    )

    return itens


# ============================================================
# DOWNLOAD DE IMAGENS
# ============================================================

async def baixar_imagem(session, url):
    if not url:
        return None

    try:

        timeout = aiohttp.ClientTimeout(total=10)

        async with session.get(
            url,
            timeout=timeout
        ) as response:

            if response.status != 200:
                return None

            tamanho = response.headers.get(
                "Content-Length"
            )

            if tamanho:

                try:
                    if int(tamanho) > MAX_IMAGEM_DOWNLOAD:
                        return None
                except Exception:
                    pass

            dados = bytearray()

            while True:

                bloco = await response.content.read(64 * 1024)

                if not bloco:
                    break

                dados.extend(bloco)

                if len(dados) > MAX_IMAGEM_DOWNLOAD:
                    return None

            return bytes(dados)

    except Exception as erro:

        print(
            f"[IMAGEM] Erro ao baixar: {erro}"
        )

        return None


# ============================================================
# PROCESSAMENTO DA IMAGEM
# ============================================================

def redimensionar_centralizado(
    imagem,
    largura,
    altura
):
    """
    Redimensiona mantendo proporção e centraliza.
    """

    imagem = imagem.convert("RGB")

    proporcao = min(
        largura / imagem.width,
        altura / imagem.height
    )

    nova_largura = max(
        1,
        int(imagem.width * proporcao)
    )

    nova_altura = max(
        1,
        int(imagem.height * proporcao)
    )

    imagem = imagem.resize(
        (nova_largura, nova_altura),
        Image.Resampling.LANCZOS
    )

    fundo = Image.new(
        "RGB",
        (largura, altura),
        COR_AREA_IMAGEM
    )

    x = (largura - nova_largura) // 2
    y = (altura - nova_altura) // 2

    fundo.paste(
        imagem,
        (x, y)
    )

    return fundo


# ============================================================
# GERAR IMAGEM DA LOJA
# ============================================================

async def gerar_imagem_loja(itens):
    """
    Cria a imagem somente com os itens novos do dia.

    O JPEG é salvo diretamente em disco para reduzir
    o consumo de RAM no Deploy Hatch.
    """

    if not itens:
        return None

    quantidade = len(itens)

    linhas = (
        quantidade + COLUNAS - 1
    ) // COLUNAS

    altura = (
        MARGEM_TOPO
        + linhas * CARD_ALTURA
        + max(0, linhas - 1) * ESPACO_VERTICAL
        + 35
    )

    print(
        f"[IMAGEM] Criando imagem "
        f"{LARGURA_FINAL}x{altura}"
    )

    # --------------------------------------------------------
    # FUNDO
    # --------------------------------------------------------

    imagem_final = Image.new(
        "RGB",
        (LARGURA_FINAL, altura),
        COR_FUNDO
    )

    draw = ImageDraw.Draw(imagem_final)

    # Faixa superior
    draw.rectangle(
        (0, 0, LARGURA_FINAL, MARGEM_TOPO),
        fill=COR_FUNDO_2
    )

    # Linha azul
    draw.rectangle(
        (
            0,
            MARGEM_TOPO - 4,
            LARGURA_FINAL,
            MARGEM_TOPO
        ),
        fill=COR_ACCENT
    )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = "FORTNITE ITEM SHOP"

    draw.text(
        (MARGEM_LATERAL, 24),
        titulo,
        font=FONTE_TITULO,
        fill=COR_TITULO
    )

    data_texto = datetime.now(
        FUSO_BRASIL
    ).strftime("%d/%m/%Y")

    subtitulo = (
        f"ITENS ADICIONADOS HOJE • "
        f"{data_texto} • "
        f"{quantidade} itens"
    )

    draw.text(
        (
            MARGEM_LATERAL,
            68
        ),
        subtitulo,
        font=FONTE_SUBTITULO,
        fill=COR_SUBTITULO
    )

    # --------------------------------------------------------
    # HTTP SESSION
    # --------------------------------------------------------

    timeout = aiohttp.ClientTimeout(
        total=15
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        # Processa UM item por vez para economizar RAM
        for indice, item in enumerate(itens):

            coluna = indice % COLUNAS
            linha = indice // COLUNAS

            x = (
                MARGEM_LATERAL
                + coluna
                * (
                    CARD_LARGURA
                    + ESPACO_HORIZONTAL
                )
            )

            y = (
                MARGEM_TOPO
                + linha
                * (
                    CARD_ALTURA
                    + ESPACO_VERTICAL
                )
            )

            # ------------------------------------------------
            # CARD
            # ------------------------------------------------

            draw.rounded_rectangle(
                (
                    x,
                    y,
                    x + CARD_LARGURA,
                    y + CARD_ALTURA
                ),
                radius=10,
                fill=COR_CARD,
                outline=COR_CARD_BORDA,
                width=1
            )

            # ------------------------------------------------
            # IMAGEM
            # ------------------------------------------------

            dados_imagem = await baixar_imagem(
                session,
                item.get("image")
            )

            if dados_imagem:

                try:

                    from io import BytesIO

                    with BytesIO(dados_imagem) as buffer:

                        imagem_item = Image.open(
                            buffer
                        )

                        imagem_item.load()

                        imagem_item = (
                            redimensionar_centralizado(
                                imagem_item,
                                IMAGEM_LARGURA,
                                IMAGEM_ALTURA
                            )
                        )

                        draw_area_x = (
                            x
                            + (
                                CARD_LARGURA
                                - IMAGEM_LARGURA
                            ) // 2
                        )

                        draw_area_y = y + 10

                        imagem_final.paste(
                            imagem_item,
                            (
                                draw_area_x,
                                draw_area_y
                            )
                        )

                        del imagem_item

                except Exception as erro:

                    print(
                        f"[IMAGEM] Falha no item "
                        f"{indice + 1}: {erro}"
                    )

            # ------------------------------------------------
            # NOME
            # ------------------------------------------------

            nome = cortar_texto(
                draw,
                item.get("name"),
                FONTE_NOME,
                CARD_LARGURA - 20
            )

            draw.text(
                (
                    x + 10,
                    y + IMAGEM_ALTURA + 17
                ),
                nome,
                font=FONTE_NOME,
                fill=COR_BRANCO
            )

            # ------------------------------------------------
            # TIPO
            # ------------------------------------------------

            tipo = cortar_texto(
                draw,
                item.get("type"),
                FONTE_TIPO,
                CARD_LARGURA - 20
            )

            draw.text(
                (
                    x + 10,
                    y + IMAGEM_ALTURA + 40
                ),
                tipo,
                font=FONTE_TIPO,
                fill=COR_SUBTITULO
            )

            # ------------------------------------------------
            # PREÇO
            # ------------------------------------------------

            preco = item.get("price", 0)

            if preco:
                preco_texto = f"{preco:,} V-BUCKS".replace(
                    ",",
                    "."
                )
            else:
                preco_texto = "PREÇO N/D"

            draw.text(
                (
                    x + 10,
                    y + IMAGEM_ALTURA + 60
                ),
                preco_texto,
                font=FONTE_PRECO,
                fill=COR_PRECO
            )

            # Libera memória a cada item
            gc.collect()

    # --------------------------------------------------------
    # SALVAR DIRETAMENTE NO DISCO
    # --------------------------------------------------------

    arquivo = tempfile.NamedTemporaryFile(
        prefix="fortnite_shop_",
        suffix=".jpg",
        delete=False
    )

    caminho = arquivo.name
    arquivo.close()

    try:

        imagem_final.save(
            caminho,
            format="JPEG",
            quality=QUALIDADE_JPEG,
            optimize=False,
            progressive=False
        )

        print(
            f"[IMAGEM] Salva em: {caminho}"
        )

    finally:

        del draw
        del imagem_final

        gc.collect()

    return caminho


# ============================================================
# API DA LOJA
# ============================================================

async def buscar_loja():
    headers = {
        "Accept-Language": IDIOMA,
        "User-Agent": "VoidHelper/1.0"
    }

    timeout = aiohttp.ClientTimeout(
        total=20
    )

    try:

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers
        ) as session:

            async with session.get(
                FORTNITE_SHOP_URL
            ) as response:

                if response.status != 200:

                    print(
                        "[API] HTTP",
                        response.status
                    )

                    return None

                dados = await response.json()

                return dados

    except Exception as erro:

        print(
            f"[API] Erro: {erro}"
        )

        return None


# ============================================================
# ESTADO DA MENSAGEM
# ============================================================

def carregar_estado():
    try:

        if not os.path.exists(
            SHOP_STATE_FILE
        ):
            return {}

        import json

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

        import json

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
            f"[ESTADO] Erro: {erro}"
        )


# ============================================================
# ATUALIZAR LOJA NO DISCORD
# ============================================================

async def atualizar_loja():
    print(
        "\n========== VERIFICAÇÃO DA LOJA =========="
    )

    dados = await buscar_loja()

    if not dados:
        return

    shop_data = dados.get("data")

    if not isinstance(shop_data, dict):
        print(
            "[LOJA] Resposta da API sem data válida."
        )
        return

    shop_hash = (
        shop_data.get("hash")
        or shop_data.get("shopHash")
    )

    if not shop_hash:

        print(
            "[LOJA] API não retornou hash."
        )

    estado = carregar_estado()

    hash_anterior = estado.get(
        "shop_hash"
    )

    # --------------------------------------------------------
    # MESMO HASH
    # --------------------------------------------------------

    if (
        shop_hash
        and hash_anterior == shop_hash
    ):

        print(
            "[LOJA] Hash não mudou. "
            "Nenhuma atualização necessária."
        )

        return

    # --------------------------------------------------------
    # ITENS DE HOJE
    # --------------------------------------------------------

    itens = extrair_itens_do_dia(
        shop_data
    )

    if not itens:

        print(
            "[LOJA] Nenhum item com "
            "inDate de hoje."
        )

        # Guarda o hash para não ficar tentando
        # gerar a mesma coisa repetidamente.
        if shop_hash:

            estado["shop_hash"] = shop_hash

            salvar_estado(estado)

        return

    # --------------------------------------------------------
    # GERA IMAGEM
    # --------------------------------------------------------

    caminho_imagem = None

    try:

        caminho_imagem = (
            await gerar_imagem_loja(
                itens
            )
        )

        if not caminho_imagem:
            return

        canal = bot.get_channel(
            CANAL_LOJA_ID
        )

        if canal is None:

            canal = await bot.fetch_channel(
                CANAL_LOJA_ID
            )

        # ----------------------------------------------------
        # MENSAGEM EXISTENTE
        # ----------------------------------------------------

        mensagem_id = estado.get(
            "message_id"
        )

        mensagem = None

        if mensagem_id:

            try:

                mensagem = await canal.fetch_message(
                    int(mensagem_id)
                )

            except (
                discord.NotFound,
                discord.HTTPException
            ):

                mensagem = None

        arquivo = discord.File(
            caminho_imagem,
            filename="fortnite-shop.jpg"
        )

        # ----------------------------------------------------
        # EDITAR
        # ----------------------------------------------------

        if mensagem:

            await mensagem.edit(
                content=(
                    "🛒 **Loja do Fortnite — "
                    "Itens adicionados hoje**"
                ),
                attachments=[arquivo]
            )

            print(
                "[DISCORD] Mensagem da loja atualizada."
            )

        # ----------------------------------------------------
        # CRIAR
        # ----------------------------------------------------

        else:

            mensagem = await canal.send(
                content=(
                    "🛒 **Loja do Fortnite — "
                    "Itens adicionados hoje**"
                ),
                file=arquivo
            )

            estado["message_id"] = (
                mensagem.id
            )

            print(
                "[DISCORD] Nova mensagem criada."
            )

        # ----------------------------------------------------
        # SALVAR ESTADO
        # ----------------------------------------------------

        if shop_hash:

            estado["shop_hash"] = (
                shop_hash
            )

        estado["data"] = (
            obter_data_brasil().isoformat()
        )

        estado["itens"] = len(itens)

        salvar_estado(estado)

    except Exception as erro:

        print(
            f"[LOJA] Erro ao atualizar Discord: "
            f"{erro}"
        )

    finally:

        if caminho_imagem:

            try:
                os.remove(
                    caminho_imagem
                )

            except Exception:
                pass

        gc.collect()


# ============================================================
# LOOP AUTOMÁTICO
# ============================================================

@tasks.loop(seconds=INTERVALO_VERIFICACAO)
async def verificar_loja():

    try:

        await atualizar_loja()

    except Exception as erro:

        print(
            f"[LOOP] Erro: {erro}"
        )


@verificar_loja.before_loop
async def antes_verificar_loja():

    await bot.wait_until_ready()


# ============================================================
# TESTE MANUAL
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    await ctx.send(
        "🔄 Consultando os itens adicionados hoje..."
    )

    try:

        dados = await buscar_loja()

        if not dados:

            await ctx.send(
                "❌ Não consegui acessar a API."
            )

            return

        shop_data = dados.get("data")

        itens = extrair_itens_do_dia(
            shop_data
        )

        if not itens:

            await ctx.send(
                "⚠️ Nenhum item foi identificado "
                "como adicionado hoje."
            )

            return

        caminho = await gerar_imagem_loja(
            itens
        )

        if not caminho:

            await ctx.send(
                "❌ Não consegui gerar a imagem."
            )

            return

        try:

            await ctx.send(
                content=(
                    f"🛒 **{len(itens)} itens "
                    f"adicionados hoje**"
                ),
                file=discord.File(
                    caminho,
                    filename="fortnite-shop.jpg"
                )
            )

        finally:

            try:
                os.remove(caminho)
            except Exception:
                pass

    except Exception as erro:

        print(
            f"[TESTE] {erro}"
        )

        await ctx.send(
            "❌ Erro ao testar a loja."
        )


# ============================================================
# REAÇÕES — NÃO ALTERAR
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
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        "=========================================="
    )

    print(
        f"🤖 Bot conectado como {bot.user}"
    )

    print(
        f"🛒 Canal da loja: {CANAL_LOJA_ID}"
    )

    print(
        f"🟢 Canal de reações: {CANAL_REACOES_ID}"
    )

    print(
        f"📐 Imagem: {LARGURA_FINAL}px"
    )

    print(
        f"📦 Colunas: {COLUNAS}"
    )

    print(
        f"📅 Filtro: somente itens de hoje"
    )

    print(
        "=========================================="
    )

    if not verificar_loja.is_running():

        verificar_loja.start()

        # Faz uma primeira consulta imediatamente,
        # sem precisar esperar 5 minutos.
        asyncio.create_task(
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