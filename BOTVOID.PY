import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import io
import json
import os
import time
import gc

from PIL import Image, ImageDraw, ImageFont, ImageFile


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CANAL_REACOES_ID = 1556998399461691443
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

IDIOMA = "pt-BR"

# Verificação da API a cada 5 minutos
INTERVALO_VERIFICACAO = 300

# Estado persistente
SHOP_STATE_FILE = "shop_state.json"


# ============================================================
# CONFIGURAÇÃO DA IMAGEM
# ============================================================

# A imagem é criada pelo próprio bot.
# Nenhum background externo é utilizado.

LARGURA_FINAL = 1200

COLUNAS = 4

MARGEM_LATERAL = 28
MARGEM_TOPO = 115

ESPACO_HORIZONTAL = 12
ESPACO_VERTICAL = 14

CARD_LARGURA = 277
CARD_ALTURA = 205

IMAGEM_LARGURA = 250
IMAGEM_ALTURA = 130

ALTURA_MAXIMA = 5000

QUALIDADE_JPEG = 60

MAX_IMAGEM_DOWNLOAD = 1 * 1024 * 1024

MAX_OFERTAS = 80


# ============================================================
# PILLOW
# ============================================================

ImageFile.LOAD_TRUNCATED_IMAGES = True

Image.MAX_IMAGE_PIXELS = 2_000_000


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
# CORES
# ============================================================

COR_FUNDO = (10, 12, 20)

COR_FUNDO_SECUNDARIO = (15, 18, 30)

COR_CARD = (21, 24, 38)

COR_CARD_BORDA = (48, 54, 78)

COR_AREA_IMAGEM = (12, 15, 25)

COR_TITULO = (255, 255, 255)

COR_SUBTITULO = (170, 178, 200)

COR_PRECO = (255, 211, 66)

COR_TIPO = (135, 145, 175)

COR_DESTAQUE = (65, 105, 255)


# ============================================================
# ESTADO
# ============================================================

def carregar_estado():

    if not os.path.exists(SHOP_STATE_FILE):

        return {
            "shop_hash": None,
            "message_id": None
        }

    try:

        with open(
            SHOP_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            dados = json.load(arquivo)

        return {
            "shop_hash": dados.get("shop_hash"),
            "message_id": dados.get("message_id")
        }

    except Exception as erro:

        print(
            f"[AVISO] Não foi possível ler o estado: {erro}"
        )

        return {
            "shop_hash": None,
            "message_id": None
        }


def salvar_estado(
    shop_hash,
    message_id
):

    try:

        dados = {
            "shop_hash": shop_hash,
            "message_id": message_id
        }

        with open(
            SHOP_STATE_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                dados,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

    except Exception as erro:

        print(
            f"[AVISO] Não foi possível salvar estado: {erro}"
        )


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(
    tamanho,
    negrito=False
):

    if negrito:

        caminhos = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf"
        ]

    else:

        caminhos = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf"
        ]

    for caminho in caminhos:

        try:

            return ImageFont.truetype(
                caminho,
                tamanho
            )

        except Exception:

            continue

    return ImageFont.load_default()


# ============================================================
# TEXTO
# ============================================================

def medir_texto(
    draw,
    texto,
    fonte
):

    try:

        caixa = draw.textbbox(
            (0, 0),
            texto,
            font=fonte
        )

        return (
            caixa[2] - caixa[0],
            caixa[3] - caixa[1]
        )

    except Exception:

        return 0, 0


def texto_centralizado(
    draw,
    x1,
    y1,
    x2,
    y2,
    texto,
    fonte,
    cor
):

    largura, altura = medir_texto(
        draw,
        texto,
        fonte
    )

    x = x1 + (
        (x2 - x1 - largura) / 2
    )

    y = y1 + (
        (y2 - y1 - altura) / 2
    )

    draw.text(
        (x, y),
        texto,
        font=fonte,
        fill=cor
    )


def limitar_texto(
    draw,
    texto,
    fonte,
    largura_maxima
):

    if not texto:
        return ""

    largura, _ = medir_texto(
        draw,
        texto,
        fonte
    )

    if largura <= largura_maxima:

        return texto

    resultado = ""

    for caractere in texto:

        tentativa = (
            resultado
            + caractere
            + "..."
        )

        largura_teste, _ = medir_texto(
            draw,
            tentativa,
            fonte
        )

        if largura_teste > largura_maxima:

            break

        resultado += caractere

    return resultado + "..."


# ============================================================
# DOWNLOAD DAS IMAGENS DOS ITENS
# ============================================================

async def baixar_imagem(
    session,
    url
):

    if not url:
        return None

    try:

        timeout = aiohttp.ClientTimeout(
            total=12
        )

        async with session.get(
            url,
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:

                print(
                    f"[AVISO] Imagem retornou HTTP "
                    f"{resposta.status}"
                )

                return None

            tamanho = resposta.content_length

            if (
                tamanho
                and tamanho > MAX_IMAGEM_DOWNLOAD
            ):

                print(
                    "[AVISO] Imagem muito grande."
                )

                return None

            dados = await resposta.read()

            if len(dados) > MAX_IMAGEM_DOWNLOAD:

                print(
                    "[AVISO] Download ultrapassou o limite."
                )

                return None

            return dados

    except asyncio.CancelledError:

        raise

    except Exception as erro:

        print(
            f"[AVISO] Erro baixando imagem: {erro}"
        )

        return None


# ============================================================
# IMAGEM DO ITEM
# ============================================================

async def processar_imagem_item(
    session,
    url
):

    dados = await baixar_imagem(
        session,
        url
    )

    if not dados:

        return None

    imagem = None
    resultado = None

    try:

        imagem = Image.open(
            io.BytesIO(dados)
        )

        # Reduz imediatamente.
        imagem.thumbnail(
            (
                IMAGEM_LARGURA,
                IMAGEM_ALTURA
            ),
            Image.Resampling.LANCZOS
        )

        if "A" in imagem.getbands():

            resultado = imagem.convert(
                "RGBA"
            )

        else:

            resultado = imagem.convert(
                "RGB"
            )

        return resultado

    except Exception as erro:

        print(
            f"[AVISO] Erro processando item: {erro}"
        )

        if resultado:

            resultado.close()

        return None

    finally:

        if imagem:

            try:
                imagem.close()
            except Exception:
                pass

        dados = None

        gc.collect()


# ============================================================
# CRIA O FUNDO
# ============================================================

def criar_fundo(
    altura
):

    altura = min(
        altura,
        ALTURA_MAXIMA
    )

    imagem = Image.new(
        "RGB",
        (
            LARGURA_FINAL,
            altura
        ),
        COR_FUNDO
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # ========================================================
    # FUNDO EM CAMADAS
    # ========================================================

    # Faixa superior
    draw.rectangle(
        (
            0,
            0,
            LARGURA_FINAL,
            MARGEM_TOPO
        ),
        fill=COR_FUNDO_SECUNDARIO
    )

    # Linha de destaque
    draw.rectangle(
        (
            0,
            MARGEM_TOPO - 2,
            LARGURA_FINAL,
            MARGEM_TOPO
        ),
        fill=COR_DESTAQUE
    )

    # ========================================================
    # DETALHES DISCRETOS
    # ========================================================

    for x in range(
        0,
        LARGURA_FINAL,
        80
    ):

        draw.line(
            (
                x,
                0,
                x + 100,
                MARGEM_TOPO
            ),
            fill=(18, 22, 36),
            width=1
        )

    # ========================================================
    # TÍTULO
    # ========================================================

    fonte_titulo = carregar_fonte(
        30,
        negrito=True
    )

    fonte_subtitulo = carregar_fonte(
        13
    )

    texto_centralizado(
        draw,
        0,
        18,
        LARGURA_FINAL,
        58,
        "FORTNITE ITEM SHOP",
        fonte_titulo,
        COR_TITULO
    )

    texto_centralizado(
        draw,
        0,
        60,
        LARGURA_FINAL,
        85,
        "LOJA DE ITENS",
        fonte_subtitulo,
        COR_SUBTITULO
    )

    return imagem


# ============================================================
# DADOS DA OFERTA
# ============================================================

def obter_nome(
    entry
):

    nome = (
        entry.get("displayName")
        or entry.get("name")
        or entry.get("devName")
    )

    if nome:

        return str(nome)

    items = entry.get(
        "items"
    )

    if isinstance(items, list):

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                continue

            nome = (
                item.get("displayName")
                or item.get("name")
            )

            if nome:

                return str(nome)

    return "Item da Loja"


def obter_preco(
    entry
):

    preco = (
        entry.get("finalPrice")
        if entry.get("finalPrice") is not None
        else entry.get("price")
    )

    if preco is None:

        return "Preço indisponível"

    try:

        return (
            f"{int(preco):,}".replace(
                ",",
                "."
            )
            + " V-Bucks"
        )

    except Exception:

        return f"{preco} V-Bucks"


def obter_tipo(
    entry
):

    items = entry.get(
        "items"
    )

    if isinstance(items, list):

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                continue

            tipo = item.get(
                "type"
            )

            if isinstance(
                tipo,
                dict
            ):

                valor = (
                    tipo.get("displayValue")
                    or tipo.get("value")
                )

                if valor:

                    return str(valor)

            if isinstance(
                tipo,
                str
            ):

                return tipo

            rarity = item.get(
                "rarity"
            )

            if isinstance(
                rarity,
                dict
            ):

                valor = (
                    rarity.get("displayValue")
                    or rarity.get("value")
                )

                if valor:

                    return str(valor)

            if isinstance(
                rarity,
                str
            ):

                return rarity

    return "Loja"


def obter_imagem_oferta(
    entry
):

    # ========================================================
    # TENTA ITEMS
    # ========================================================

    items = entry.get(
        "items"
    )

    if isinstance(
        items,
        list
    ):

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                continue

            images = item.get(
                "images"
            )

            if isinstance(
                images,
                dict
            ):

                imagem = (
                    images.get("featured")
                    or images.get("icon")
                    or images.get("background")
                )

                if imagem:

                    return imagem

            imagem = item.get(
                "image"
            )

            if imagem:

                return imagem

    # ========================================================
    # GRANTED
    # ========================================================

    granted = entry.get(
        "granted"
    )

    if isinstance(
        granted,
        list
    ):

        for item in granted:

            if not isinstance(
                item,
                dict
            ):

                continue

            images = item.get(
                "images"
            )

            if isinstance(
                images,
                dict
            ):

                imagem = (
                    images.get("featured")
                    or images.get("icon")
                    or images.get("background")
                )

                if imagem:

                    return imagem

            imagem = item.get(
                "image"
            )

            if imagem:

                return imagem

    # ========================================================
    # IMAGES DIRETO
    # ========================================================

    images = entry.get(
        "images"
    )

    if isinstance(
        images,
        dict
    ):

        return (
            images.get("featured")
            or images.get("icon")
            or images.get("background")
        )

    return None


# ============================================================
# EXTRAIR OFERTAS
# ============================================================

def extrair_ofertas(
    loja
):

    entries = loja.get(
        "entries"
    )

    if not isinstance(
        entries,
        list
    ):

        print(
            "[ERRO] API não retornou entries."
        )

        return []

    ofertas = []

    for entry in entries:

        if not isinstance(
            entry,
            dict
        ):

            continue

        ofertas.append(
            {
                "nome": obter_nome(
                    entry
                ),
                "preco": obter_preco(
                    entry
                ),
                "tipo": obter_tipo(
                    entry
                ),
                "imagem": obter_imagem_oferta(
                    entry
                )
            }
        )

    return ofertas


# ============================================================
# CONSULTAR API
# ============================================================

async def consultar_loja(
    session
):

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        async with session.get(
            FORTNITE_SHOP_URL,
            params={
                "language": IDIOMA
            },
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:

                print(
                    f"[ERRO] API HTTP "
                    f"{resposta.status}"
                )

                return None

            resultado = await resposta.json()

            if not isinstance(
                resultado,
                dict
            ):

                return None

            loja = resultado.get(
                "data"
            )

            if not isinstance(
                loja,
                dict
            ):

                return None

            return loja

    except asyncio.CancelledError:

        raise

    except Exception as erro:

        print(
            f"[ERRO] API Fortnite: {erro}"
        )

        return None


# ============================================================
# GERAR IMAGEM
# ============================================================

async def gerar_imagem_loja(
    session,
    ofertas
):

    if not ofertas:

        return None

    # Segurança contra respostas gigantes.
    ofertas = ofertas[
        :MAX_OFERTAS
    ]

    linhas = (
        len(ofertas)
        + COLUNAS
        - 1
    ) // COLUNAS

    altura = (
        MARGEM_TOPO
        + (
            linhas
            * CARD_ALTURA
        )
        + (
            max(
                0,
                linhas - 1
            )
            * ESPACO_VERTICAL
        )
        + 30
    )

    altura = min(
        altura,
        ALTURA_MAXIMA
    )

    print(
        f"[IMAGEM] Criando "
        f"{LARGURA_FINAL}x{altura}"
    )

    canvas = criar_fundo(
        altura
    )

    draw = ImageDraw.Draw(
        canvas
    )

    fonte_nome = carregar_fonte(
        14,
        negrito=True
    )

    fonte_preco = carregar_fonte(
        13,
        negrito=True
    )

    fonte_tipo = carregar_fonte(
        10
    )

    # ========================================================
    # CARDS
    # ========================================================

    for indice, oferta in enumerate(
        ofertas
    ):

        coluna = (
            indice
            % COLUNAS
        )

        linha = (
            indice
            // COLUNAS
        )

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

        # ====================================================
        # CARD
        # ====================================================

        draw.rounded_rectangle(
            (
                x,
                y,
                x + CARD_LARGURA,
                y + CARD_ALTURA
            ),
            radius=12,
            fill=COR_CARD,
            outline=COR_CARD_BORDA,
            width=1
        )

        # ====================================================
        # ÁREA DA IMAGEM
        # ====================================================

        area_x1 = x + 12
        area_y1 = y + 10

        area_x2 = (
            x
            + CARD_LARGURA
            - 12
        )

        area_y2 = (
            y
            + 10
            + IMAGEM_ALTURA
        )

        draw.rounded_rectangle(
            (
                area_x1,
                area_y1,
                area_x2,
                area_y2
            ),
            radius=9,
            fill=COR_AREA_IMAGEM
        )

        # ====================================================
        # IMAGEM
        # ====================================================

        imagem = None

        try:

            imagem = await processar_imagem_item(
                session,
                oferta.get(
                    "imagem"
                )
            )

            if imagem:

                pos_x = (
                    x
                    + (
                        CARD_LARGURA
                        - imagem.width
                    )
                    // 2
                )

                pos_y = (
                    y
                    + 10
                    + (
                        IMAGEM_ALTURA
                        - imagem.height
                    )
                    // 2
                )

                if imagem.mode == "RGBA":

                    canvas.paste(
                        imagem,
                        (
                            pos_x,
                            pos_y
                        ),
                        imagem
                    )

                else:

                    canvas.paste(
                        imagem,
                        (
                            pos_x,
                            pos_y
                        )
                    )

        except Exception as erro:

            print(
                f"[AVISO] Erro no item "
                f"{indice + 1}: {erro}"
            )

        finally:

            if imagem:

                try:
                    imagem.close()
                except Exception:
                    pass

            imagem = None

            gc.collect()

        # ====================================================
        # NOME
        # ====================================================

        nome = limitar_texto(
            draw,
            oferta.get(
                "nome",
                "Item"
            ),
            fonte_nome,
            CARD_LARGURA - 20
        )

        texto_centralizado(
            draw,
            x + 8,
            y + 143,
            x + CARD_LARGURA - 8,
            y + 164,
            nome,
            fonte_nome,
            COR_TITULO
        )

        # ====================================================
        # PREÇO
        # ====================================================

        preco = oferta.get(
            "preco",
            ""
        )

        texto_centralizado(
            draw,
            x + 8,
            y + 164,
            x + CARD_LARGURA - 8,
            y + 184,
            preco,
            fonte_preco,
            COR_PRECO
        )

        # ====================================================
        # TIPO
        # ====================================================

        tipo = limitar_texto(
            draw,
            oferta.get(
                "tipo",
                "Loja"
            ),
            fonte_tipo,
            CARD_LARGURA - 20
        )

        texto_centralizado(
            draw,
            x + 8,
            y + 184,
            x + CARD_LARGURA - 8,
            y + 200,
            tipo,
            fonte_tipo,
            COR_TIPO
        )

        await asyncio.sleep(0)

    # ========================================================
    # EXPORTAR
    # ========================================================

    buffer = io.BytesIO()

    try:

        canvas.save(
            buffer,
            format="JPEG",
            quality=QUALIDADE_JPEG,
            optimize=False,
            progressive=False
        )

        buffer.seek(0)

        tamanho = (
            len(buffer.getbuffer())
            / 1024
            / 1024
        )

        print(
            f"[IMAGEM] Tamanho final: "
            f"{tamanho:.2f} MB"
        )

        return buffer

    except Exception as erro:

        print(
            f"[ERRO] Salvando JPEG: {erro}"
        )

        buffer.close()

        return None

    finally:

        canvas.close()

        gc.collect()


# ============================================================
# BUSCAR MENSAGEM EXISTENTE
# ============================================================

async def buscar_mensagem(
    canal,
    message_id
):

    if not message_id:

        return None

    try:

        return await canal.fetch_message(
            int(message_id)
        )

    except discord.NotFound:

        print(
            "[AVISO] Mensagem anterior não existe."
        )

        return None

    except discord.HTTPException as erro:

        print(
            f"[AVISO] Erro buscando mensagem: {erro}"
        )

        return None


# ============================================================
# PUBLICAR
# ============================================================

async def publicar_loja(
    canal,
    shop_hash,
    ofertas
):

    estado = carregar_estado()

    message_id = estado.get(
        "message_id"
    )

    imagem = await gerar_imagem_loja(
        bot.http_session,
        ofertas
    )

    if imagem is None:

        print(
            "[ERRO] Não foi possível gerar a imagem."
        )

        return False

    arquivo = None

    try:

        arquivo = discord.File(
            imagem,
            filename="fortnite-shop.jpg"
        )

        agora = time.strftime(
            "%d/%m/%Y às %H:%M"
        )

        embed = discord.Embed(
            title="🛒 LOJA FORTNITE",
            description=(
                f"**Loja atualizada:** {agora}\n"
                f"🎮 **{len(ofertas)} itens disponíveis**"
            ),
            color=discord.Color.blurple()
        )

        embed.set_image(
            url="attachment://fortnite-shop.jpg"
        )

        embed.set_footer(
            text="VoidHelper • Atualização automática"
        )

        mensagem = await buscar_mensagem(
            canal,
            message_id
        )

        if mensagem:

            await mensagem.edit(
                embed=embed,
                attachments=[
                    arquivo
                ]
            )

            novo_id = mensagem.id

            print(
                "[LOJA] Mensagem atualizada."
            )

        else:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo
            )

            novo_id = mensagem.id

            print(
                "[LOJA] Nova mensagem criada."
            )

        salvar_estado(
            shop_hash,
            novo_id
        )

        return True

    except discord.HTTPException as erro:

        print(
            f"[ERRO] Discord: {erro}"
        )

        return False

    except Exception as erro:

        print(
            f"[ERRO] Publicação: {erro}"
        )

        return False

    finally:

        if arquivo:

            try:
                arquivo.close()
            except Exception:
                pass

        try:
            imagem.close()
        except Exception:
            pass

        gc.collect()


# ============================================================
# VERIFICAR LOJA
# ============================================================

async def verificar_loja(
    forcar=False
):

    canal = bot.get_channel(
        CANAL_LOJA_ID
    )

    if canal is None:

        print(
            "[ERRO] Canal da loja não encontrado."
        )

        return

    loja = await consultar_loja(
        bot.http_session
    )

    if loja is None:

        return

    shop_hash = (
        loja.get("hash")
        or loja.get("shopHash")
    )

    if not shop_hash:

        print(
            "[ERRO] Hash da loja não encontrado."
        )

        return

    estado = carregar_estado()

    hash_anterior = estado.get(
        "shop_hash"
    )

    print(
        f"[LOJA] Hash atual: {shop_hash}"
    )

    # ========================================================
    # LOJA NÃO MUDOU
    # ========================================================

    if (
        hash_anterior == shop_hash
        and not forcar
    ):

        print(
            "[LOJA] Nenhuma alteração."
        )

        return

    # ========================================================
    # LOJA MUDOU
    # ========================================================

    if hash_anterior is None:

        print(
            "[LOJA] Primeira publicação."
        )

    else:

        print(
            "=============================================="
        )

        print(
            "[LOJA] 🔄 NOVA LOJA DETECTADA"
        )

        print(
            f"[LOJA] Hash antigo: {hash_anterior}"
        )

        print(
            f"[LOJA] Hash novo:   {shop_hash}"
        )

        print(
            "=============================================="
        )

    ofertas = extrair_ofertas(
        loja
    )

    print(
        f"[LOJA] Total de ofertas: {len(ofertas)}"
    )

    if not ofertas:

        print(
            "[ERRO] Nenhuma oferta encontrada."
        )

        return

    sucesso = await publicar_loja(
        canal,
        shop_hash,
        ofertas
    )

    if sucesso:

        print(
            "[LOJA] ✅ Loja publicada com sucesso."
        )


# ============================================================
# LOOP
# ============================================================

@tasks.loop(
    seconds=INTERVALO_VERIFICACAO
)
async def verificar_loja_loop():

    print(
        "[LOJA] 🔎 Verificando loja..."
    )

    await verificar_loja()


@verificar_loja_loop.before_loop
async def iniciar_monitoramento():

    await bot.wait_until_ready()

    print(
        "[LOJA] Monitoramento iniciado."
    )

    print(
        "[LOJA] Verificação automática a cada "
        f"{INTERVALO_VERIFICACAO // 60} minutos."
    )


# ============================================================
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        "=============================================="
    )

    print(
        f"[BOT] Online: {bot.user}"
    )

    print(
        f"[BOT] ID: {bot.user.id}"
    )

    print(
        "[BOT] VoidHelper iniciado."
    )

    print(
        "=============================================="
    )

    if not verificar_loja_loop.is_running():

        verificar_loja_loop.start()


# ============================================================
# REAÇÕES
# ============================================================

@bot.event
async def on_message(message):

    if message.author.bot:

        return

    # ========================================================
    # SISTEMA ORIGINAL — NÃO ALTERADO
    # ========================================================

    if message.channel.id == CANAL_REACOES_ID:

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

            print(
                "[REAÇÕES] 🟢 ⚖️ 🔴 adicionados."
            )

        except discord.HTTPException as erro:

            print(
                f"[REAÇÕES] Erro: {erro}"
            )

    await bot.process_commands(
        message
    )


# ============================================================
# !TESTELOJA
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    await ctx.send(
        "🔄 Gerando a loja atual..."
    )

    await verificar_loja(
        forcar=True
    )

    try:

        await ctx.message.delete()

    except Exception:

        pass


@teste_loja.error
async def erro_teste_loja(
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
            f"[ERRO] !testeloja: {erro}"
        )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

async def iniciar():

    if not TOKEN:

        print(
            "=============================================="
        )

        print(
            "[ERRO] DISCORD_TOKEN não configurado."
        )

        print(
            "=============================================="
        )

        return

    bot.http_session = aiohttp.ClientSession(
        headers={
            "User-Agent":
                "VoidHelper/1.0"
        }
    )

    try:

        await bot.start(
            TOKEN
        )

    finally:

        if hasattr(
            bot,
            "http_session"
        ):

            if not bot.http_session.closed:

                await bot.http_session.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            iniciar()
        )

    except KeyboardInterrupt:

        print(
            "[BOT] Encerrado."
        )

    except Exception as erro:

        print(
            f"[ERRO FATAL] {erro}"
        )