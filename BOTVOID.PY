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

# API Fortnite
FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

# Idioma
IDIOMA = "pt-BR"

# Verificação a cada 5 minutos
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


# ============================================================
# IMAGEM FINAL
# ============================================================

# Reduzido de 1536 para diminuir bastante o consumo de RAM.
LARGURA_FINAL = 1200

COLUNAS = 4

MARGEM_LATERAL = 30
MARGEM_TOPO = 190

ESPACO_HORIZONTAL = 12
ESPACO_VERTICAL = 14

CARD_LARGURA = 277
CARD_ALTURA = 205

IMAGEM_LARGURA = 250
IMAGEM_ALTURA = 135


# ============================================================
# CONTROLE DE MEMÓRIA
# ============================================================

# Limite de download de cada imagem.
MAX_IMAGEM_DOWNLOAD = 1 * 1024 * 1024

# Limite do background.
MAX_BACKGROUND_DOWNLOAD = 4 * 1024 * 1024

# Máximo de pixels para uma imagem de item.
MAX_PIXELS_IMAGEM = 2_000_000

# Qualidade final.
QUALIDADE_JPEG = 60

# Altura máxima absoluta da imagem.
# Evita que uma loja excepcionalmente grande consuma RAM.
ALTURA_MAXIMA = 5000


ImageFile.LOAD_TRUNCATED_IMAGES = True

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

            pass

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
# DOWNLOAD
# ============================================================

async def baixar_imagem(
    session,
    url,
    limite
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
                    f"[AVISO] HTTP {resposta.status}"
                )

                return None

            tamanho = resposta.content_length

            if tamanho and tamanho > limite:

                print(
                    "[AVISO] Imagem acima do limite."
                )

                return None

            dados = await resposta.read()

            if len(dados) > limite:

                print(
                    "[AVISO] Download acima do limite."
                )

                return None

            return dados

    except asyncio.CancelledError:

        raise

    except Exception as erro:

        print(
            f"[AVISO] Erro no download: {erro}"
        )

        return None


# ============================================================
# BACKGROUND
# ============================================================

async def carregar_fundo(
    session
):

    dados = await baixar_imagem(
        session,
        FUNDO_URL,
        MAX_BACKGROUND_DOWNLOAD
    )

    if not dados:
        return None

    original = None
    fundo = None

    try:

        original = Image.open(
            io.BytesIO(dados)
        )

        original.load()

        print(
            f"[FUNDO] {original.width}x{original.height}"
        )

        fundo = original.convert(
            "RGB"
        )

        # Redimensiona diretamente para 1200 px.
        if fundo.width != LARGURA_FINAL:

            proporcao = (
                LARGURA_FINAL
                / fundo.width
            )

            nova_altura = int(
                fundo.height
                * proporcao
            )

            reduzido = fundo.resize(
                (
                    LARGURA_FINAL,
                    nova_altura
                ),
                Image.Resampling.LANCZOS
            )

            fundo.close()

            fundo = reduzido

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

        if original:

            try:
                original.close()
            except Exception:
                pass

        dados = None

        gc.collect()


# ============================================================
# DADOS DA OFERTA
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
# EXTRAI OFERTAS
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
# CONSULTAR API
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
            f"[ERRO] API: {erro}"
        )

        return None


# ============================================================
# PROCESSAR ITEM
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
        MAX_IMAGEM_DOWNLOAD
    )

    if not dados:
        return None

    original = None
    resultado = None

    try:

        original = Image.open(
            io.BytesIO(dados)
        )

        largura = original.width
        altura = original.height

        if largura <= 0 or altura <= 0:
            return None

        # Reduz a imagem imediatamente.
        original.thumbnail(
            (
                IMAGEM_LARGURA,
                IMAGEM_ALTURA
            ),
            Image.Resampling.LANCZOS
        )

        # Só depois da redução fazemos a conversão.
        if "A" in original.getbands():

            resultado = original.convert(
                "RGBA"
            )

        else:

            resultado = original.convert(
                "RGB"
            )

        return resultado

    except Exception as erro:

        print(
            f"[AVISO] Erro imagem: {erro}"
        )

        if resultado:

            try:
                resultado.close()
            except Exception:
                pass

        return None

    finally:

        if original:

            try:
                original.close()
            except Exception:
                pass

        dados = None

        gc.collect()


# ============================================================
# PREPARAR CANVAS
# ============================================================

def preparar_canvas(
    fundo,
    altura
):

    if altura <= fundo.height:

        return fundo

    # Nunca deixa a imagem ficar
    # absurdamente alta.
    altura = min(
        altura,
        ALTURA_MAXIMA
    )

    canvas = Image.new(
        "RGB",
        (
            LARGURA_FINAL,
            altura
        ),
        (18, 18, 23)
    )

    canvas.paste(
        fundo,
        (0, 0)
    )

    # Pequena faixa do rodapé.
    faixa_altura = min(
        160,
        fundo.height
    )

    inicio = (
        fundo.height
        - faixa_altura
    )

    faixa = fundo.crop(
        (
            0,
            inicio,
            fundo.width,
            fundo.height
        )
    )

    y = fundo.height

    while y < altura:

        restante = min(
            faixa.height,
            altura - y
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
                y
            )
        )

        parte.close()

        y += restante

    faixa.close()
    fundo.close()

    gc.collect()

    return canvas


# ============================================================
# GERAR IMAGEM
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

    # ========================================================
    # LIMITA A QUANTIDADE DE ITENS
    # ========================================================
    #
    # Evita que uma resposta anormal da API
    # crie uma imagem gigantesca.
    #
    MAX_OFERTAS = 80

    if len(ofertas) > MAX_OFERTAS:

        print(
            f"[AVISO] API retornou {len(ofertas)} itens."
        )

        print(
            f"[AVISO] Limitando para {MAX_OFERTAS}."
        )

        ofertas = ofertas[:MAX_OFERTAS]

    fundo = await carregar_fundo(
        session
    )

    if fundo is None:
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
        + 30
    )

    altura_final = max(
        fundo.height,
        altura_grid
    )

    altura_final = min(
        altura_final,
        ALTURA_MAXIMA
    )

    print(
        f"[IMAGEM] {LARGURA_FINAL}x{altura_final}"
    )

    canvas = preparar_canvas(
        fundo,
        altura_final
    )

    draw = ImageDraw.Draw(
        canvas
    )

    fonte_nome = carregar_fonte(
        15,
        negrito=True
    )

    fonte_preco = carregar_fonte(
        14,
        negrito=True
    )

    fonte_tipo = carregar_fonte(
        11
    )

    # ========================================================
    # ITENS
    # ========================================================

    for indice, oferta in enumerate(
        ofertas
    ):

        coluna = (
            indice % COLUNAS
        )

        linha = (
            indice // COLUNAS
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
            radius=14,
            fill=(18, 18, 24),
            outline=(255, 255, 255),
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
            radius=10,
            fill=(30, 30, 38)
        )

        # ====================================================
        # IMAGEM
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
                f"[AVISO] Item {indice + 1}: "
                f"{erro}"
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
            y + 147,
            x + CARD_LARGURA - 8,
            y + 169,
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
            x + 8,
            y + 168,
            x + CARD_LARGURA - 8,
            y + 188,
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
            CARD_LARGURA - 20
        )

        texto_centralizado(
            draw,
            x + 8,
            y + 188,
            x + CARD_LARGURA - 8,
            y + 202,
            tipo,
            fonte_tipo,
            (190, 190, 200)
        )

        await asyncio.sleep(0)

    # ========================================================
    # JPEG
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

        tamanho_mb = (
            len(buffer.getbuffer())
            / 1024
            / 1024
        )

        print(
            f"[IMAGEM] JPEG final: "
            f"{tamanho_mb:.2f} MB"
        )

        return buffer

    except Exception as erro:

        print(
            f"[ERRO] JPEG: {erro}"
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
            f"[AVISO] Erro Discord: {erro}"
        )

        return None


# ============================================================
# PUBLICAR LOJA
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
        "[IMAGEM] Gerando loja..."
    )

    imagem = await gerar_imagem_loja(
        bot.http_session,
        ofertas
    )

    if imagem is None:

        print(
            "[ERRO] Imagem não gerada."
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
                "[OK] Mensagem editada."
            )

        else:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo
            )

            message_id = mensagem.id

            print(
                "[OK] Mensagem criada."
            )

        salvar_estado(
            shop_hash,
            message_id
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
            "[ERRO] Hash não encontrado."
        )

        return

    estado = carregar_estado()

    hash_anterior = estado.get(
        "shop_hash"
    )

    print(
        f"[LOJA] Hash: {shop_hash}"
    )

    # ========================================================
    # MESMA LOJA
    # ========================================================

    if (
        hash_anterior == shop_hash
        and not forcar
    ):

        print(
            "[LOJA] Sem alterações."
        )

        return

    # ========================================================
    # ALTERAÇÃO
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
            "[LOJA] NOVA LOJA!"
        )

        print(
            f"[LOJA] Antigo: {hash_anterior}"
        )

        print(
            f"[LOJA] Novo:   {shop_hash}"
        )

        print(
            "=============================================="
        )

    ofertas = extrair_ofertas(
        loja
    )

    print(
        f"[LOJA] Ofertas: {len(ofertas)}"
    )

    if not ofertas:

        print(
            "[ERRO] Nenhuma oferta."
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
# LOOP AUTOMÁTICO
# ============================================================

@tasks.loop(
    seconds=INTERVALO_VERIFICACAO
)
async def verificar_loja_loop():

    print(
        "[LOJA] Consultando Fortnite API..."
    )

    await verificar_loja()


@verificar_loja_loop.before_loop
async def iniciar_monitoramento():

    await bot.wait_until_ready()

    print(
        "[LOJA] Monitoramento iniciado."
    )

    # IMPORTANTE:
    # Não gera a imagem imediatamente no startup.
    #
    # O primeiro ciclo será executado pelo loop
    # após o bot estar completamente estabilizado.
    print(
        "[LOJA] Primeira consulta será feita "
        "pelo ciclo automático."
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
        f"[BOT] Online como: {bot.user}"
    )

    print(
        f"[BOT] ID: {bot.user.id}"
    )

    print(
        "[BOT] Memória otimizada para Deploy Hatch."
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
    # SISTEMA ORIGINAL
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
# COMANDO !TESTELOJA
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