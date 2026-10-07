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

# Canal onde o bot adiciona 🟢 ⚖️ 🔴
CANAL_REACOES_ID = 1556998399461691443

# Canal da loja Fortnite
CANAL_LOJA_ID = 1214658145243234324

# API da loja Fortnite
FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

# Idioma
IDIOMA = "pt-BR"

# Verifica a API a cada 5 minutos
INTERVALO_VERIFICACAO = 300


# ============================================================
# BACKGROUND
# ============================================================

FUNDO_URL = (
    "https://media.discordapp.net/attachments/"
    "671152891360313385/1296301322030678081/"
    "17-10-2024_v1.png"
    "?ex=6ac7022f&is=6ac5b0af"
    "&hm=77c4b5e93762a727d49ef75813aac00e0208e2e076d73272dd252fe4fda82969"
    "&=&format=webp&quality=lossless&width=1536&height=1027"
)

LARGURA_FINAL = 1536


# ============================================================
# LAYOUT
# ============================================================

COLUNAS = 4

MARGEM_LATERAL = 45
MARGEM_TOPO = 245

ESPACO_HORIZONTAL = 18
ESPACO_VERTICAL = 20

CARD_LARGURA = 345
CARD_ALTURA = 250

IMAGEM_LARGURA = 315
IMAGEM_ALTURA = 175


# ============================================================
# MEMÓRIA / IMAGENS
# ============================================================

# Limite de download de uma imagem individual
MAX_IMAGEM_DOWNLOAD = 2 * 1024 * 1024

# Limite do background
MAX_BACKGROUND_DOWNLOAD = 6 * 1024 * 1024

# Evita imagens absurdamente grandes
MAX_PIXELS_IMAGEM = 4_000_000

# JPEG final
QUALIDADE_JPEG = 68


# Permite que Pillow continue trabalhando com imagens
# parcialmente carregadas.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Proteção contra imagens com milhões de pixels.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS_IMAGEM


# ============================================================
# ESTADO
# ============================================================

SHOP_STATE_FILE = "shop_state.json"


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
# ESTADO DA LOJA
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
            f"[AVISO] Erro lendo estado: {erro}"
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
            f"[AVISO] Erro salvando estado: {erro}"
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

    x = x1 + ((x2 - x1 - largura) / 2)
    y = y1 + ((y2 - y1 - altura) / 2)

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
# DOWNLOAD SEGURO
# ============================================================

async def baixar_imagem(
    session,
    url,
    limite=MAX_IMAGEM_DOWNLOAD
):

    if not url:
        return None

    try:

        timeout = aiohttp.ClientTimeout(
            total=15
        )

        async with session.get(
            url,
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:

                print(
                    f"[AVISO] HTTP {resposta.status}"
                )

                return None

            tamanho = resposta.content_length

            if tamanho and tamanho > limite:

                print(
                    "[AVISO] Imagem maior que o limite."
                )

                return None

            dados = await resposta.read()

            if len(dados) > limite:

                print(
                    "[AVISO] Download excedeu o limite."
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
# CARREGAR BACKGROUND
# ============================================================

async def carregar_fundo(
    session
):

    dados = await baixar_imagem(
        session,
        FUNDO_URL,
        limite=MAX_BACKGROUND_DOWNLOAD
    )

    if not dados:
        return None

    imagem_original = None
    fundo = None

    try:

        imagem_original = Image.open(
            io.BytesIO(dados)
        )

        largura = imagem_original.width
        altura = imagem_original.height

        print(
            f"[FUNDO] Original: {largura}x{altura}"
        )

        # Carrega somente em RGB.
        # Evita RGBA e reduz bastante o consumo.
        imagem_original.load()

        fundo = imagem_original.convert(
            "RGB"
        )

        if fundo.width != LARGURA_FINAL:

            proporcao = (
                LARGURA_FINAL
                / fundo.width
            )

            nova_altura = int(
                fundo.height * proporcao
            )

            novo_fundo = fundo.resize(
                (
                    LARGURA_FINAL,
                    nova_altura
                ),
                Image.Resampling.LANCZOS
            )

            fundo.close()

            fundo = novo_fundo

        return fundo

    except Exception as erro:

        print(
            f"[ERRO] Background: {erro}"
        )

        if fundo:

            try:
                fundo.close()
            except Exception:
                pass

        return None

    finally:

        if imagem_original:

            try:
                imagem_original.close()
            except Exception:
                pass

        dados = None

        gc.collect()


# ============================================================
# IMAGEM DA OFERTA
# ============================================================

def obter_imagem_oferta(
    entry
):

    items = entry.get("items")

    if isinstance(items, list):

        for item in items:

            if not isinstance(item, dict):
                continue

            images = item.get("images")

            if isinstance(images, dict):

                imagem = (
                    images.get("featured")
                    or images.get("icon")
                    or images.get("background")
                )

                if imagem:
                    return imagem

            imagem = item.get("image")

            if imagem:
                return imagem

    granted = entry.get("granted")

    if isinstance(granted, list):

        for item in granted:

            if not isinstance(item, dict):
                continue

            images = item.get("images")

            if isinstance(images, dict):

                imagem = (
                    images.get("featured")
                    or images.get("icon")
                    or images.get("background")
                )

                if imagem:
                    return imagem

            imagem = item.get("image")

            if imagem:
                return imagem

    images = entry.get("images")

    if isinstance(images, dict):

        return (
            images.get("featured")
            or images.get("icon")
            or images.get("background")
        )

    return None


# ============================================================
# NOME
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

    items = entry.get("items")

    if isinstance(items, list):

        for item in items:

            if isinstance(item, dict):

                nome_item = (
                    item.get("name")
                    or item.get("displayName")
                )

                if nome_item:
                    return str(nome_item)

    return "Item da Loja"


# ============================================================
# PREÇO
# ============================================================

def obter_preco(
    entry
):

    if entry.get("finalPrice") is not None:

        preco = entry.get(
            "finalPrice"
        )

    else:

        preco = entry.get(
            "price"
        )

    if preco is None:
        return "Preço indisponível"

    try:

        valor = int(preco)

        return (
            f"{valor:,}".replace(",", ".")
            + " V-Bucks"
        )

    except Exception:

        return f"{preco} V-Bucks"


# ============================================================
# TIPO
# ============================================================

def obter_tipo(
    entry
):

    items = entry.get("items")

    if isinstance(items, list):

        for item in items:

            if not isinstance(item, dict):
                continue

            tipo = item.get("type")

            if isinstance(tipo, dict):

                valor = (
                    tipo.get("displayValue")
                    or tipo.get("value")
                )

                if valor:
                    return str(valor)

            if isinstance(tipo, str):
                return tipo

            rarity = item.get(
                "rarity"
            )

            if isinstance(rarity, dict):

                valor = (
                    rarity.get("displayValue")
                    or rarity.get("value")
                )

                if valor:
                    return str(valor)

            if isinstance(rarity, str):
                return rarity

    return "Loja"


# ============================================================
# OFERTAS
# ============================================================

def extrair_ofertas(
    loja
):

    entries = loja.get(
        "entries"
    )

    if not isinstance(entries, list):

        print(
            "[ERRO] API não retornou entries."
        )

        return []

    ofertas = []

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        ofertas.append(
            {
                "nome": obter_nome(entry),
                "preco": obter_preco(entry),
                "tipo": obter_tipo(entry),
                "imagem": obter_imagem_oferta(entry)
            }
        )

    return ofertas


# ============================================================
# FORTNITE API
# ============================================================

async def consultar_loja(
    session
):

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        parametros = {
            "language": IDIOMA
        }

        async with session.get(
            FORTNITE_SHOP_URL,
            params=parametros,
            timeout=timeout
        ) as resposta:

            if resposta.status != 200:

                print(
                    f"[ERRO] Fortnite API HTTP "
                    f"{resposta.status}"
                )

                return None

            resultado = await resposta.json()

            if not isinstance(resultado, dict):
                return None

            loja = resultado.get(
                "data"
            )

            if not isinstance(loja, dict):
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
# PROCESSA UMA IMAGEM DE ITEM
# ============================================================

async def processar_imagem_item(
    session,
    url
):

    if not url:
        return None

    dados = await baixar_imagem(
        session,
        url,
        limite=MAX_IMAGEM_DOWNLOAD
    )

    if not dados:
        return None

    imagem_original = None
    imagem_final = None

    try:

        # Abre sem carregar imediatamente.
        imagem_original = Image.open(
            io.BytesIO(dados)
        )

        largura = imagem_original.width
        altura = imagem_original.height

        # Evita imagens absurdamente grandes.
        if (
            largura * altura
            > MAX_PIXELS_IMAGEM
        ):

            print(
                f"[IMAGEM] Muito grande: "
                f"{largura}x{altura}"
            )

            # Reduz antes do load quando possível.
            imagem_original.thumbnail(
                (
                    IMAGEM_LARGURA,
                    IMAGEM_ALTURA
                ),
                Image.Resampling.LANCZOS
            )

        else:

            imagem_original.thumbnail(
                (
                    IMAGEM_LARGURA,
                    IMAGEM_ALTURA
                ),
                Image.Resampling.LANCZOS
            )

        # RGB/RGBA somente no tamanho pequeno.
        if "A" in imagem_original.getbands():

            imagem_final = imagem_original.convert(
                "RGBA"
            )

        else:

            imagem_final = imagem_original.convert(
                "RGB"
            )

        return imagem_final

    except Exception as erro:

        print(
            f"[AVISO] Erro processando item: {erro}"
        )

        if imagem_final:

            try:
                imagem_final.close()
            except Exception:
                pass

        return None

    finally:

        if imagem_original:

            try:
                imagem_original.close()
            except Exception:
                pass

        dados = None

        gc.collect()


# ============================================================
# ESTENDE BACKGROUND
# ============================================================

def preparar_canvas(
    fundo,
    altura_final
):

    if altura_final <= fundo.height:

        return fundo

    canvas = Image.new(
        "RGB",
        (
            LARGURA_FINAL,
            altura_final
        ),
        (18, 18, 23)
    )

    canvas.paste(
        fundo,
        (0, 0)
    )

    # Copia somente uma faixa pequena
    # do final do background.
    faixa_altura = 180

    inicio = max(
        0,
        fundo.height - faixa_altura
    )

    faixa = fundo.crop(
        (
            0,
            inicio,
            fundo.width,
            fundo.height
        )
    )

    # Não precisamos redimensionar.
    # O background já possui a largura correta.
    posicao_y = fundo.height

    while posicao_y < altura_final:

        restante = min(
            faixa.height,
            altura_final - posicao_y
        )

        parte = faixa.crop(
            (
                0,
                0,
                faixa.width,
                restante
            )
        )

        canvas.paste(
            parte,
            (
                0,
                posicao_y
            )
        )

        parte.close()

        posicao_y += restante

    faixa.close()
    fundo.close()

    gc.collect()

    return canvas


# ============================================================
# GERA IMAGEM DA LOJA
# ============================================================

async def gerar_imagem_loja(
    session,
    ofertas
):

    if not ofertas:

        print(
            "[ERRO] Nenhuma oferta."
        )

        return None

    fundo = await carregar_fundo(
        session
    )

    if fundo is None:

        print(
            "[ERRO] Não foi possível carregar fundo."
        )

        return None

    quantidade_linhas = (
        len(ofertas)
        + COLUNAS
        - 1
    ) // COLUNAS

    altura_grid = (
        MARGEM_TOPO
        + (
            quantidade_linhas
            * CARD_ALTURA
        )
        + (
            max(
                0,
                quantidade_linhas - 1
            )
            * ESPACO_VERTICAL
        )
        + 50
    )

    altura_final = max(
        fundo.height,
        altura_grid
    )

    print(
        f"[IMAGEM] Ofertas: {len(ofertas)}"
    )

    print(
        f"[IMAGEM] Altura final: "
        f"{altura_final}px"
    )

    canvas = preparar_canvas(
        fundo,
        altura_final
    )

    draw = ImageDraw.Draw(
        canvas
    )

    fonte_nome = carregar_fonte(
        19,
        negrito=True
    )

    fonte_preco = carregar_fonte(
        17,
        negrito=True
    )

    fonte_tipo = carregar_fonte(
        13,
        negrito=False
    )

    # ========================================================
    # PROCESSA ITEM POR ITEM
    # ========================================================

    for indice, oferta in enumerate(ofertas):

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
            radius=18,
            fill=(18, 18, 24),
            outline=(255, 255, 255),
            width=2
        )

        # ====================================================
        # ÁREA DA IMAGEM
        # ====================================================

        area_x1 = x + 15
        area_y1 = y + 12
        area_x2 = (
            x
            + CARD_LARGURA
            - 15
        )
        area_y2 = (
            y
            + 12
            + IMAGEM_ALTURA
        )

        draw.rounded_rectangle(
            (
                area_x1,
                area_y1,
                area_x2,
                area_y2
            ),
            radius=12,
            fill=(30, 30, 38)
        )

        # ====================================================
        # IMAGEM DO ITEM
        # ====================================================

        imagem = None

        try:

            imagem = await processar_imagem_item(
                session,
                oferta.get("imagem")
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
                    + 12
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
                f"[AVISO] Imagem do item "
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
            CARD_LARGURA - 24
        )

        texto_centralizado(
            draw,
            x + 10,
            y + 190,
            x + CARD_LARGURA - 10,
            y + 215,
            nome,
            fonte_nome,
            (255, 255, 255)
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
            x + 10,
            y + 213,
            x + CARD_LARGURA - 10,
            y + 237,
            preco,
            fonte_preco,
            (255, 220, 70)
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
            CARD_LARGURA - 24
        )

        texto_centralizado(
            draw,
            x + 10,
            y + 236,
            x + CARD_LARGURA - 10,
            y + 255,
            tipo,
            fonte_tipo,
            (190, 190, 200)
        )

        # Pequena pausa para não monopolizar CPU
        await asyncio.sleep(0)

    # ========================================================
    # SALVA JPEG
    # ========================================================

    buffer = io.BytesIO()

    try:

        canvas.save(
            buffer,
            format="JPEG",
            quality=QUALIDADE_JPEG,
            optimize=True,
            progressive=True
        )

        buffer.seek(0)

        print(
            f"[IMAGEM] Gerada: "
            f"{len(buffer.getbuffer()) / 1024 / 1024:.2f} MB"
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
# BUSCAR MENSAGEM
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
            "[AVISO] Mensagem antiga não encontrada."
        )

        return None

    except discord.HTTPException as erro:

        print(
            f"[AVISO] Erro buscando mensagem: {erro}"
        )

        return None


# ============================================================
# PUBLICAR / EDITAR
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

    print(
        "[IMAGEM] Gerando imagem..."
    )

    imagem = await gerar_imagem_loja(
        bot.http_session,
        ofertas
    )

    if imagem is None:

        print(
            "[ERRO] Falha gerando imagem."
        )

        return False

    try:

        arquivo = discord.File(
            imagem,
            filename="fortnite-shop.jpg"
        )

        data = time.strftime(
            "%d/%m/%Y"
        )

        hora = time.strftime(
            "%H:%M"
        )

        embed = discord.Embed(
            title="🛒 LOJA FORTNITE",
            description=(
                f"**Loja atualizada em "
                f"{data} às {hora}**\n\n"
                f"🎮 {len(ofertas)} ofertas disponíveis"
            ),
            color=discord.Color.blurple()
        )

        embed.set_image(
            url="attachment://fortnite-shop.jpg"
        )

        embed.set_footer(
            text="Atualização automática • VoidHelper"
        )

        mensagem = await buscar_mensagem(
            canal,
            message_id
        )

        if mensagem:

            await mensagem.edit(
                content=None,
                embed=embed,
                attachments=[arquivo]
            )

            message_id = mensagem.id

            print(
                "[OK] Mensagem da loja editada."
            )

        else:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo
            )

            message_id = mensagem.id

            print(
                "[OK] Mensagem da loja criada."
            )

        salvar_estado(
            shop_hash,
            message_id
        )

        return True

    except discord.HTTPException as erro:

        print(
            f"[ERRO] Discord HTTP: {erro}"
        )

        return False

    except Exception as erro:

        print(
            f"[ERRO] Publicando loja: {erro}"
        )

        return False

    finally:

        try:
            imagem.close()
        except Exception:
            pass

        gc.collect()


# ============================================================
# VERIFICA LOJA
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

    # ========================================================
    # HASH
    # ========================================================

    shop_hash = (
        loja.get("hash")
        or loja.get("shopHash")
    )

    if not shop_hash:

        print(
            "[ERRO] API não retornou hash."
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
    # MESMA LOJA
    # ========================================================

    if (
        hash_anterior == shop_hash
        and not forcar
    ):

        print(
            "[LOJA] Nenhuma mudança."
        )

        return

    # ========================================================
    # NOVA LOJA
    # ========================================================

    if hash_anterior is None:

        print(
            "[LOJA] Primeira execução."
        )

    else:

        print(
            "=============================================="
        )

        print(
            "[LOJA] NOVA LOJA DETECTADA!"
        )

        print(
            f"[LOJA] Anterior: {hash_anterior}"
        )

        print(
            f"[LOJA] Novo:     {shop_hash}"
        )

        print(
            "=============================================="
        )

    ofertas = extrair_ofertas(
        loja
    )

    print(
        f"[LOJA] Ofertas encontradas: "
        f"{len(ofertas)}"
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
            "[LOJA] Atualização concluída."
        )


# ============================================================
# LOOP
# ============================================================

@tasks.loop(
    seconds=INTERVALO_VERIFICACAO
)
async def verificar_loja_loop():

    print(
        "[LOJA] Verificando Fortnite API..."
    )

    await verificar_loja()


@verificar_loja_loop.before_loop
async def iniciar_monitoramento():

    await bot.wait_until_ready()

    print(
        "[LOJA] Monitoramento iniciado."
    )

    # Primeira verificação imediata
    await verificar_loja()


# ============================================================
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        "=============================================="
    )

    print(
        f"[BOT] Online como: {bot.user}"
    )

    print(
        f"[BOT] ID: {bot.user.id}"
    )

    print(
        "=============================================="
    )

    if not verificar_loja_loop.is_running():

        verificar_loja_loop.start()


# ============================================================
# SISTEMA ORIGINAL DE REAÇÕES
# ============================================================

@bot.event
async def on_message(message):

    # Ignora bots
    if message.author.bot:
        return

    # ========================================================
    # NÃO ALTERADO
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
# COMANDO MANUAL
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    await ctx.send(
        "🔄 Atualizando a imagem da loja atual..."
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
            "[ERRO] DISCORD_TOKEN não configurado!"
        )

        print(
            "Configure DISCORD_TOKEN no Deploy Hatch."
        )

        print(
            "=============================================="
        )

        return

    bot.http_session = aiohttp.ClientSession(
        headers={
            "User-Agent": (
                "VoidHelper/1.0 "
                "Discord Fortnite Shop Bot"
            )
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
            "[BOT] Bot encerrado."
        )

    except Exception as erro:

        print(
            f"[ERRO FATAL] {erro}"
        )