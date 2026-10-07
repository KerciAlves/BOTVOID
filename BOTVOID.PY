import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import gc
import json
import os
import tempfile

from datetime import datetime
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

INTERVALO_VERIFICACAO = 300

SHOP_STATE_FILE = "shop_state.json"

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


# ============================================================
# CONFIGURAÇÃO DA IMAGEM
# ============================================================

LARGURA_FINAL = 1200
COLUNAS = 4

MARGEM_LATERAL = 28
MARGEM_TOPO = 120

ESPACO_HORIZONTAL = 12
ESPACO_VERTICAL = 14

CARD_LARGURA = (
    LARGURA_FINAL
    - (MARGEM_LATERAL * 2)
    - (ESPACO_HORIZONTAL * (COLUNAS - 1))
) // COLUNAS

CARD_ALTURA = 230

IMAGEM_LARGURA = CARD_LARGURA - 20
IMAGEM_ALTURA = 145

QUALIDADE_JPEG = 60

MAX_IMAGEM_DOWNLOAD = 1 * 1024 * 1024

ImageFile.LOAD_TRUNCATED_IMAGES = True
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
FONTE_RARIDADE = carregar_fonte(13)


# ============================================================
# UTILIDADES
# ============================================================

def cortar_texto(draw, texto, fonte, largura_max):
    texto = str(texto or "Sem nome")

    if draw.textbbox((0, 0), texto, font=fonte)[2] <= largura_max:
        return texto

    while len(texto) > 3:
        texto = texto[:-1]
        teste = texto + "..."

        if draw.textbbox((0, 0), teste, font=fonte)[2] <= largura_max:
            return teste

    return "..."


def converter_data(data):
    if not data:
        return None

    if not isinstance(data, str):
        return None

    try:
        texto = data.strip()

        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"

        return datetime.fromisoformat(texto)

    except Exception:
        return None


# ============================================================
# ESTADO
# ============================================================

def carregar_estado():
    try:
        if not os.path.exists(SHOP_STATE_FILE):
            return {}

        with open(
            SHOP_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:
            return json.load(arquivo)

    except Exception as erro:
        print(f"[ESTADO] Erro ao carregar: {erro}")
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
        print(f"[ESTADO] Erro ao salvar: {erro}")


# ============================================================
# EXTRAIR ITENS DA ATUALIZAÇÃO ATUAL
# ============================================================

def extrair_itens_atualizados(shop_data):

    if not isinstance(shop_data, dict):
        return []

    entries = shop_data.get("entries", [])

    if not isinstance(entries, list):
        print("[LOJA] entries não é uma lista.")
        return []

    data_loja_texto = shop_data.get("date")
    data_loja = converter_data(data_loja_texto)

    if data_loja is None:
        print("[LOJA] Não consegui interpretar a data da loja.")
        return []

    data_loja_dia = data_loja.date()

    print("")
    print("==========================================")
    print("INFORMAÇÕES DA LOJA")
    print("==========================================")
    print(f"Data da loja: {data_loja}")
    print(f"Dia da loja: {data_loja_dia}")
    print(f"Total de entries: {len(entries)}")
    print("==========================================")

    itens = []
    ids_adicionados = set()

    for numero, entry in enumerate(entries, start=1):

        if not isinstance(entry, dict):
            continue

        in_date_texto = entry.get("inDate")
        in_date = converter_data(in_date_texto)

        if in_date is None:
            print(f"[ENTRY {numero}] inDate inválido.")
            continue

        # SOMENTE ENTRADAS DA DATA ATUAL DA LOJA
        if in_date.date() != data_loja_dia:
            continue

        print("")
        print(f"[ENTRY {numero}] ITEM DA ATUALIZAÇÃO")
        print(f"inDate: {in_date}")
        print(f"offerId: {entry.get('offerId')}")

        preco = entry.get("finalPrice", 0)

        try:
            preco = int(preco)
        except Exception:
            preco = 0

        br_items = entry.get("brItems", [])

        if not isinstance(br_items, list):
            continue

        if not br_items:
            print("Nenhum brItem encontrado.")
            continue

        for item in br_items:

            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if not item_id:
                item_id = entry.get("offerId")

            if not item_id:
                item_id = item.get("name")

            if not item_id:
                continue

            item_id = str(item_id)

            if item_id in ids_adicionados:
                continue

            ids_adicionados.add(item_id)

            nome = item.get(
                "name",
                "Item Fortnite"
            )

            # -----------------------------
            # RARIDADE
            # -----------------------------

            rarity = item.get("rarity", {})

            if isinstance(rarity, dict):
                raridade = (
                    rarity.get("displayValue")
                    or rarity.get("value")
                    or "Item"
                )
            else:
                raridade = "Item"

            # -----------------------------
            # IMAGEM
            # -----------------------------

            images = item.get("images", {})

            imagem = None

            if isinstance(images, dict):

                imagem = (
                    images.get("featured")
                    or images.get("icon")
                    or images.get("smallIcon")
                )

            if not imagem:
                imagem = item.get("image")

            print(f"  Nome: {nome}")
            print(f"  Raridade: {raridade}")
            print(f"  Preço: {preco}")
            print(
                f"  Imagem: "
                f"{'SIM' if imagem else 'NÃO'}"
            )

            itens.append({
                "id": item_id,
                "name": nome,
                "rarity": raridade,
                "image": imagem,
                "price": preco,
                "in_date": in_date.isoformat(),
                "offer_id": str(
                    entry.get("offerId", "")
                )
            })

    print("")
    print("==========================================")
    print(f"TOTAL DE ITENS DE HOJE: {len(itens)}")
    print("==========================================")

    return itens


# ============================================================
# BAIXAR IMAGEM
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

                bloco = await response.content.read(
                    64 * 1024
                )

                if not bloco:
                    break

                dados.extend(bloco)

                if len(dados) > MAX_IMAGEM_DOWNLOAD:
                    return None

            return bytes(dados)

    except Exception as erro:

        print(f"[IMAGEM] Erro ao baixar: {erro}")

        return None


# ============================================================
# PREPARAR IMAGEM
# ============================================================

def preparar_imagem(dados, largura, altura):

    from io import BytesIO

    try:

        with BytesIO(dados) as buffer:

            imagem = Image.open(buffer)

            imagem.load()

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
                (
                    nova_largura,
                    nova_altura
                ),
                Image.Resampling.LANCZOS
            )

            resultado = Image.new(
                "RGB",
                (
                    largura,
                    altura
                ),
                COR_AREA_IMAGEM
            )

            x = (
                largura - nova_largura
            ) // 2

            y = (
                altura - nova_altura
            ) // 2

            resultado.paste(
                imagem,
                (x, y)
            )

            imagem.close()

            return resultado

    except Exception as erro:

        print(
            f"[IMAGEM] Erro ao processar: {erro}"
        )

        return None


# ============================================================
# GERAR IMAGEM DA LOJA
# ============================================================

async def gerar_imagem_loja(itens):

    if not itens:
        return None

    quantidade = len(itens)

    linhas = (
        quantidade + COLUNAS - 1
    ) // COLUNAS

    altura = (
        MARGEM_TOPO
        + (
            linhas * CARD_ALTURA
        )
        + (
            max(0, linhas - 1)
            * ESPACO_VERTICAL
        )
        + 35
    )

    print(
        f"[IMAGEM] Gerando "
        f"{LARGURA_FINAL}x{altura}"
    )

    imagem_final = Image.new(
        "RGB",
        (
            LARGURA_FINAL,
            altura
        ),
        COR_FUNDO
    )

    draw = ImageDraw.Draw(
        imagem_final
    )

    # ========================================================
    # CABEÇALHO
    # ========================================================

    draw.rectangle(
        (
            0,
            0,
            LARGURA_FINAL,
            MARGEM_TOPO
        ),
        fill=COR_FUNDO_2
    )

    draw.rectangle(
        (
            0,
            MARGEM_TOPO - 4,
            LARGURA_FINAL,
            MARGEM_TOPO
        ),
        fill=COR_ACCENT
    )

    draw.text(
        (
            MARGEM_LATERAL,
            25
        ),
        "FORTNITE ITEM SHOP",
        font=FONTE_TITULO,
        fill=COR_TITULO
    )

    data_atual = datetime.now(
        FUSO_BRASIL
    )

    subtitulo = (
        f"ITENS DA ATUALIZAÇÃO • "
        f"{data_atual.strftime('%d/%m/%Y')} • "
        f"{quantidade} itens"
    )

    draw.text(
        (
            MARGEM_LATERAL,
            70
        ),
        subtitulo,
        font=FONTE_SUBTITULO,
        fill=COR_SUBTITULO
    )

    # ========================================================
    # DOWNLOAD E MONTAGEM
    # ========================================================

    timeout = aiohttp.ClientTimeout(
        total=15
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        for indice, item in enumerate(itens):

            coluna = indice % COLUNAS
            linha = indice // COLUNAS

            x = (
                MARGEM_LATERAL
                + coluna * (
                    CARD_LARGURA
                    + ESPACO_HORIZONTAL
                )
            )

            y = (
                MARGEM_TOPO
                + linha * (
                    CARD_ALTURA
                    + ESPACO_VERTICAL
                )
            )

            # =================================================
            # CARD
            # =================================================

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

            # =================================================
            # IMAGEM
            # =================================================

            dados = await baixar_imagem(
                session,
                item.get("image")
            )

            if dados:

                imagem_item = preparar_imagem(
                    dados,
                    IMAGEM_LARGURA,
                    IMAGEM_ALTURA
                )

                if imagem_item:

                    imagem_x = (
                        x
                        + (
                            CARD_LARGURA
                            - IMAGEM_LARGURA
                        ) // 2
                    )

                    imagem_y = y + 8

                    imagem_final.paste(
                        imagem_item,
                        (
                            imagem_x,
                            imagem_y
                        )
                    )

                    imagem_item.close()

            # =================================================
            # NOME
            # =================================================

            nome = cortar_texto(
                draw,
                item.get("name"),
                FONTE_NOME,
                CARD_LARGURA - 20
            )

            draw.text(
                (
                    x + 10,
                    y + IMAGEM_ALTURA + 15
                ),
                nome,
                font=FONTE_NOME,
                fill=COR_BRANCO
            )

            # =================================================
            # RARIDADE
            # =================================================

            raridade = cortar_texto(
                draw,
                item.get("rarity"),
                FONTE_RARIDADE,
                CARD_LARGURA - 20
            )

            draw.text(
                (
                    x + 10,
                    y + IMAGEM_ALTURA + 39
                ),
                raridade,
                font=FONTE_RARIDADE,
                fill=COR_SUBTITULO
            )

            # =================================================
            # PREÇO
            # =================================================

            preco = item.get(
                "price",
                0
            )

            if preco:

                preco_texto = (
                    f"{preco:,} V-BUCKS"
                    .replace(",", ".")
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

            del dados

            gc.collect()

    # ========================================================
    # SALVAR JPEG NO DISCO
    # ========================================================

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
# BUSCAR LOJA
# ============================================================

async def buscar_loja():

    parametros = {
        "language": IDIOMA
    }

    headers = {
        "User-Agent": "VoidHelper/1.0",
        "Accept": "application/json"
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
                FORTNITE_SHOP_URL,
                params=parametros
            ) as response:

                print(
                    f"[API] Status: {response.status}"
                )

                if response.status != 200:

                    texto = await response.text()

                    print(
                        f"[API] Resposta: "
                        f"{texto[:500]}"
                    )

                    return None

                return await response.json()

    except Exception as erro:

        print(
            f"[API] Erro: {erro}"
        )

        return None


# ============================================================
# ATUALIZAR LOJA
# ============================================================

async def atualizar_loja():

    print("")
    print("==========================================")
    print("VERIFICANDO LOJA DO FORTNITE")
    print("==========================================")

    dados = await buscar_loja()

    if not dados:
        return

    shop_data = dados.get("data")

    if not isinstance(shop_data, dict):

        print(
            "[LOJA] Resposta inválida."
        )

        return

    shop_hash = (
        shop_data.get("hash")
        or shop_data.get("shopHash")
    )

    shop_date = shop_data.get(
        "date"
    )

    print(f"[LOJA] Hash: {shop_hash}")
    print(f"[LOJA] Data: {shop_date}")

    estado = carregar_estado()

    hash_anterior = estado.get(
        "shop_hash"
    )

    # ========================================================
    # HASH NÃO MUDOU
    # ========================================================

    if (
        shop_hash
        and hash_anterior == shop_hash
    ):

        print(
            "[LOJA] Loja não mudou."
        )

        return

    # ========================================================
    # EXTRAIR SOMENTE OS ITENS DA ATUALIZAÇÃO
    # ========================================================

    itens = extrair_itens_atualizados(
        shop_data
    )

    if not itens:

        print(
            "[LOJA] Nenhum item encontrado."
        )

        return

    print(
        f"[LOJA] {len(itens)} itens encontrados."
    )

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

        mensagem = None

        mensagem_id = estado.get(
            "message_id"
        )

        # ====================================================
        # PEGAR MENSAGEM EXISTENTE
        # ====================================================

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

        # ====================================================
        # EDITAR
        # ====================================================

        if mensagem:

            await mensagem.edit(
                content=(
                    "🛒 **Loja do Fortnite — "
                    "Itens da atualização atual**"
                ),
                attachments=[arquivo]
            )

            print(
                "[DISCORD] Mensagem atualizada."
            )

        # ====================================================
        # CRIAR
        # ====================================================

        else:

            mensagem = await canal.send(
                content=(
                    "🛒 **Loja do Fortnite — "
                    "Itens da atualização atual**"
                ),
                file=arquivo
            )

            estado["message_id"] = (
                mensagem.id
            )

            print(
                "[DISCORD] Mensagem criada."
            )

        # ====================================================
        # SALVAR ESTADO
        # ====================================================

        estado["shop_hash"] = shop_hash
        estado["shop_date"] = shop_date
        estado["items_count"] = len(itens)

        salvar_estado(
            estado
        )

    except Exception as erro:

        print(
            f"[LOJA] Erro: {erro}"
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

@tasks.loop(
    seconds=INTERVALO_VERIFICACAO
)
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
# COMANDO DE TESTE
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    await ctx.send(
        "🔄 Consultando a atualização atual da loja..."
    )

    try:

        dados = await buscar_loja()

        if not dados:

            await ctx.send(
                "❌ Não consegui acessar a API."
            )

            return

        shop_data = dados.get(
            "data"
        )

        if not isinstance(
            shop_data,
            dict
        ):

            await ctx.send(
                "❌ Dados da loja inválidos."
            )

            return

        itens = extrair_itens_atualizados(
            shop_data
        )

        if not itens:

            await ctx.send(
                "⚠️ Nenhum item foi encontrado "
                "na atualização atual."
            )

            return

        await ctx.send(
            f"🔎 Encontrei **{len(itens)} itens**. "
            f"Gerando imagem..."
        )

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
                    f"da atualização atual**"
                ),
                file=discord.File(
                    caminho,
                    filename="fortnite-shop.jpg"
                )
            )

        finally:

            try:
                os.remove(
                    caminho
                )
            except Exception:
                pass

    except Exception as erro:

        print(
            f"[TESTE] Erro: {erro}"
        )

        await ctx.send(
            "❌ Ocorreu um erro. "
            "Confira os logs."
        )


# ============================================================
# SISTEMA DE REAÇÕES
# NÃO ALTERAR
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

    print("")
    print("==========================================")
    print(f"🤖 Bot conectado como {bot.user}")
    print(f"🛒 Canal loja: {CANAL_LOJA_ID}")
    print(f"🟢 Canal reações: {CANAL_REACOES_ID}")
    print(f"📐 Largura imagem: {LARGURA_FINAL}px")
    print(f"📦 Colunas: {COLUNAS}")
    print("🎯 Apenas itens da atualização atual")
    print("==========================================")

    if not verificar_loja.is_running():

        verificar_loja.start()

        asyncio.create_task(
            atualizar_loja()
        )


# ============================================================
# INICIAR BOT
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi encontrada."
    )


bot.run(TOKEN)