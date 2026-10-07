import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import io
import json
import os
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# Canal onde o sistema de reações funciona
CANAL_REACOES_ID = 1556998399461691443

# Canal onde a loja do Fortnite será exibida
CANAL_LOJA_ID = 1214658145243234324

# API Fortnite
FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

# Idioma
IDIOMA = "pt-BR"

# Verificação da loja
INTERVALO_VERIFICACAO = 300  # 5 minutos

# Layout
COLUNAS = 4

CARD_LARGURA = 225
CARD_ALTURA = 265

ESPACO = 10
MARGEM = 18

# Imagem do item dentro do card
IMAGEM_LARGURA = 205
IMAGEM_ALTURA = 165

# Limites para economizar RAM
MAX_IMAGEM_DOWNLOAD = 5 * 1024 * 1024  # 5 MB

# Qualidade JPEG
JPEG_QUALITY = 72

# Arquivo que guarda o estado da loja
SHOP_STATE_FILE = "shop_state.json"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

intents.guilds = True
intents.messages = True
intents.message_content = True


# ============================================================
# BOT
# ============================================================

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(tamanho):
    """
    Tenta carregar uma fonte do sistema.
    Se não encontrar, usa a fonte padrão do Pillow.
    """

    caminhos = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for caminho in caminhos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            pass

    return ImageFont.load_default()


FONTE_TITULO = carregar_fonte(25)
FONTE_ITEM = carregar_fonte(15)
FONTE_PRECO = carregar_fonte(17)
FONTE_INFO = carregar_fonte(12)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def texto_centralizado(draw, texto, y, fonte, largura, fill):
    """
    Desenha um texto centralizado horizontalmente.
    """

    bbox = draw.textbbox((0, 0), texto, font=fonte)

    largura_texto = bbox[2] - bbox[0]

    x = (largura - largura_texto) // 2

    draw.text(
        (x, y),
        texto,
        font=fonte,
        fill=fill
    )


def limitar_texto(texto, limite=30):
    """
    Evita nomes enormes quebrando o layout.
    """

    texto = str(texto or "")

    if len(texto) <= limite:
        return texto

    return texto[:limite - 3] + "..."


def formatar_preco(preco):
    """
    Formata o preço de V-Bucks.
    """

    if preco is None:
        return "Preço N/A"

    try:
        preco = int(preco)
        return f"{preco:,} V-Bucks".replace(",", ".")
    except Exception:
        return str(preco)


def obter_cor_raridade(raridade):
    """
    Define a cor da borda de acordo com a raridade.
    """

    raridade = str(raridade or "").lower()

    if "legendary" in raridade:
        return (255, 180, 40)

    if "epic" in raridade:
        return (170, 70, 255)

    if "rare" in raridade:
        return (50, 140, 255)

    if "uncommon" in raridade:
        return (70, 200, 100)

    if "marvel" in raridade:
        return (220, 40, 40)

    if "icon" in raridade:
        return (230, 80, 180)

    if "dark" in raridade:
        return (80, 80, 90)

    return (110, 110, 120)


def obter_nome_raridade(raridade):
    """
    Traduz algumas raridades para português.
    """

    raridade = str(raridade or "").lower()

    traducoes = {
        "legendary": "Lendário",
        "epic": "Épico",
        "rare": "Raro",
        "uncommon": "Incomum",
        "common": "Comum",
        "marvel": "Marvel",
        "icon": "Ícone",
        "dark": "Sombrio"
    }

    for chave, valor in traducoes.items():
        if chave in raridade:
            return valor

    return raridade.capitalize() if raridade else "Item"


def obter_tipo_item(item):
    """
    Tenta identificar o tipo do item.
    """

    tipo = item.get("type")

    if isinstance(tipo, dict):
        nome = (
            tipo.get("displayValue")
            or tipo.get("value")
            or tipo.get("name")
        )

        if nome:
            return str(nome)

    if tipo:
        return str(tipo)

    return "Item"


def obter_imagem_item(item):
    """
    Tenta encontrar a melhor imagem disponível.
    """

    imagens = item.get("images")

    if isinstance(imagens, dict):

        possiveis = [
            "icon",
            "featured",
            "other"
        ]

        for chave in possiveis:
            valor = imagens.get(chave)

            if isinstance(valor, str) and valor.startswith("http"):
                return valor

    # Algumas versões da API podem fornecer a URL diretamente
    for chave in [
        "icon",
        "image",
        "featured"
    ]:

        valor = item.get(chave)

        if isinstance(valor, str) and valor.startswith("http"):
            return valor

    return None


def obter_nome_item(item):
    """
    Obtém o nome do item.
    """

    nome = item.get("name")

    if nome:
        return str(nome)

    nome = item.get("displayName")

    if nome:
        return str(nome)

    return "Item Fortnite"


def obter_preco_item(item):
    """
    Obtém o preço do item.
    """

    # Caso comum
    preco = item.get("price")

    if isinstance(preco, dict):
        for chave in [
            "finalPrice",
            "regularPrice",
            "price"
        ]:
            valor = preco.get(chave)

            if valor is not None:
                return valor

    if isinstance(preco, (int, float)):
        return preco

    # Outras estruturas possíveis
    for chave in [
        "finalPrice",
        "regularPrice"
    ]:
        valor = item.get(chave)

        if valor is not None:
            return valor

    return None


def obter_raridade_item(item):
    """
    Obtém a raridade do item.
    """

    raridade = item.get("rarity")

    if isinstance(raridade, dict):

        for chave in [
            "displayValue",
            "value",
            "name"
        ]:
            valor = raridade.get(chave)

            if valor:
                return str(valor)

    if raridade:
        return str(raridade)

    return ""


# ============================================================
# ESTADO DA LOJA
# ============================================================

def carregar_estado():
    """
    Carrega o estado salvo da loja.
    """

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

    except Exception:

        return {
            "shop_hash": None,
            "message_id": None
        }


def salvar_estado(shop_hash, message_id):
    """
    Salva o hash da loja e o ID da mensagem.
    """

    dados = {
        "shop_hash": shop_hash,
        "message_id": message_id
    }

    try:

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
            f"[ERRO] Não foi possível salvar estado: {erro}"
        )


# ============================================================
# DOWNLOAD DA IMAGEM
# ============================================================

async def baixar_imagem(session, url):
    """
    Baixa uma imagem por vez.

    Isso é proposital para não explodir a memória
    no plano de 256 MB.
    """

    if not url:
        return None

    try:

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        ) as resposta:

            if resposta.status != 200:
                return None

            tamanho = resposta.content_length

            if tamanho and tamanho > MAX_IMAGEM_DOWNLOAD:
                print(
                    f"[AVISO] Imagem muito grande ignorada: "
                    f"{tamanho / 1024 / 1024:.2f} MB"
                )

                return None

            dados = await resposta.read()

            if len(dados) > MAX_IMAGEM_DOWNLOAD:
                print(
                    "[AVISO] Imagem excedeu o limite de tamanho."
                )

                return None

            return dados

    except Exception as erro:

        print(
            f"[AVISO] Erro ao baixar imagem: {erro}"
        )

        return None


# ============================================================
# PREPARAR IMAGEM
# ============================================================

def preparar_imagem_item(dados):
    """
    Abre e redimensiona a imagem.

    A imagem final fica pequena para economizar RAM.
    """

    if not dados:
        return None

    imagem = None

    try:

        imagem = Image.open(
            io.BytesIO(dados)
        )

        imagem.load()

        # Converte para RGB para evitar problemas
        # com PNG/RGBA e reduzir memória.
        if imagem.mode != "RGB":
            fundo = Image.new(
                "RGB",
                imagem.size,
                (30, 30, 35)
            )

            if "A" in imagem.mode:

                imagem_rgba = imagem.convert("RGBA")

                fundo.paste(
                    imagem_rgba,
                    mask=imagem_rgba.getchannel("A")
                )

                imagem.close()

                imagem = fundo

            else:

                imagem = imagem.convert("RGB")

        # Redimensiona mantendo proporção
        imagem.thumbnail(
            (
                IMAGEM_LARGURA,
                IMAGEM_ALTURA
            ),
            Image.Resampling.LANCZOS
        )

        return imagem

    except Exception as erro:

        print(
            f"[AVISO] Erro processando imagem: {erro}"
        )

        try:
            if imagem:
                imagem.close()
        except Exception:
            pass

        return None


# ============================================================
# DESENHAR PLACEHOLDER
# ============================================================

def desenhar_placeholder(
    draw,
    x,
    y
):

    draw.rounded_rectangle(
        (
            x,
            y,
            x + IMAGEM_LARGURA,
            y + IMAGEM_ALTURA
        ),
        radius=8,
        fill=(38, 38, 45)
    )

    texto_centralizado(
        draw,
        "Sem imagem",
        y + IMAGEM_ALTURA // 2 - 10,
        FONTE_INFO,
        CARD_LARGURA,
        (170, 170, 180)
    )


# ============================================================
# DESENHAR CARD
# ============================================================

def desenhar_card(
    canvas,
    draw,
    item,
    imagem,
    x,
    y
):

    nome = obter_nome_item(item)

    preco = obter_preco_item(item)

    raridade = obter_raridade_item(item)

    tipo = obter_tipo_item(item)

    cor_raridade = obter_cor_raridade(
        raridade
    )

    raridade_nome = obter_nome_raridade(
        raridade
    )

    # --------------------------------------------------------
    # CARD
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            x,
            y,
            x + CARD_LARGURA,
            y + CARD_ALTURA
        ),
        radius=10,
        fill=(27, 27, 34),
        outline=cor_raridade,
        width=2
    )

    # --------------------------------------------------------
    # ÁREA DA IMAGEM
    # --------------------------------------------------------

    area_x = x + 10
    area_y = y + 10

    draw.rounded_rectangle(
        (
            area_x,
            area_y,
            area_x + IMAGEM_LARGURA,
            area_y + IMAGEM_ALTURA
        ),
        radius=8,
        fill=(20, 20, 25)
    )

    if imagem:

        imagem_x = (
            area_x
            + (
                IMAGEM_LARGURA
                - imagem.width
            ) // 2
        )

        imagem_y = (
            area_y
            + (
                IMAGEM_ALTURA
                - imagem.height
            ) // 2
        )

        canvas.paste(
            imagem,
            (
                imagem_x,
                imagem_y
            )
        )

    else:

        desenhar_placeholder(
            draw,
            area_x,
            area_y
        )

    # --------------------------------------------------------
    # NOME
    # --------------------------------------------------------

    nome = limitar_texto(
        nome,
        27
    )

    texto_centralizado(
        draw,
        nome,
        y + 181,
        FONTE_ITEM,
        CARD_LARGURA,
        (255, 255, 255)
    )

    # --------------------------------------------------------
    # PREÇO
    # --------------------------------------------------------

    texto_centralizado(
        draw,
        formatar_preco(preco),
        y + 207,
        FONTE_PRECO,
        CARD_LARGURA,
        (255, 220, 80)
    )

    # --------------------------------------------------------
    # RARIDADE / TIPO
    # --------------------------------------------------------

    info = f"{raridade_nome} • {tipo}"

    info = limitar_texto(
        info,
        30
    )

    texto_centralizado(
        draw,
        info,
        y + 235,
        FONTE_INFO,
        CARD_LARGURA,
        cor_raridade
    )


# ============================================================
# OBTER ITENS DA API
# ============================================================

async def obter_loja():

    try:

        timeout = aiohttp.ClientTimeout(
            total=30
        )

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "BOTVOID/1.0"
            }
        ) as session:

            params = {
                "language": IDIOMA
            }

            async with session.get(
                FORTNITE_SHOP_URL,
                params=params
            ) as resposta:

                if resposta.status != 200:

                    print(
                        f"[ERRO] API respondeu "
                        f"{resposta.status}"
                    )

                    return None

                dados = await resposta.json()

                return dados

    except Exception as erro:

        print(
            f"[ERRO] Falha ao consultar API: {erro}"
        )

        return None


# ============================================================
# EXTRAIR ITENS
# ============================================================

def extrair_itens(dados):

    if not dados:
        return []

    data = dados.get("data")

    if not isinstance(data, dict):
        return []

    itens = []

    # ========================================================
    # FORMATO MAIS COMUM
    # ========================================================

    entries = data.get("entries")

    if isinstance(entries, list):

        for entry in entries:

            if not isinstance(entry, dict):
                continue

            # Alguns entries possuem itens em "brItems"
            br_items = entry.get("brItems")

            if isinstance(br_items, list):

                for item in br_items:

                    if isinstance(item, dict):
                        itens.append(item)

            # Outros podem trazer item diretamente
            elif (
                entry.get("name")
                or entry.get("displayName")
            ):

                itens.append(entry)

    # ========================================================
    # CASO A API RETORNE "SHOP"
    # ========================================================

    shop = data.get("shop")

    if isinstance(shop, list):

        for item in shop:

            if isinstance(item, dict):
                itens.append(item)

    # ========================================================
    # REMOVER DUPLICADOS
    # ========================================================

    resultado = []

    vistos = set()

    for item in itens:

        nome = obter_nome_item(item)

        imagem = obter_imagem_item(item)

        chave = (
            nome,
            imagem
        )

        if chave in vistos:
            continue

        vistos.add(chave)

        resultado.append(item)

    return resultado


# ============================================================
# CRIAR IMAGEM DA LOJA
# ============================================================

async def criar_imagem_loja(itens):

    if not itens:

        print(
            "[AVISO] Nenhum item encontrado."
        )

        return None

    total_itens = len(itens)

    linhas = (
        total_itens + COLUNAS - 1
    ) // COLUNAS

    largura = (
        MARGEM * 2
        + COLUNAS * CARD_LARGURA
        + (COLUNAS - 1) * ESPACO
    )

    altura_cabecalho = 75

    altura = (
        MARGEM
        + altura_cabecalho
        + linhas * CARD_ALTURA
        + (linhas - 1) * ESPACO
        + MARGEM
    )

    print(
        f"[LOJA] {total_itens} itens"
    )

    print(
        f"[LOJA] Imagem: {largura}x{altura}"
    )

    # ========================================================
    # CANVAS
    # ========================================================

    canvas = Image.new(
        "RGB",
        (
            largura,
            altura
        ),
        (14, 14, 18)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # ========================================================
    # CABEÇALHO
    # ========================================================

    texto_centralizado(
        draw,
        "FORTNITE ITEM SHOP",
        15,
        FONTE_TITULO,
        largura,
        (255, 255, 255)
    )

    texto_centralizado(
        draw,
        f"{total_itens} itens disponíveis",
        47,
        FONTE_INFO,
        largura,
        (170, 170, 180)
    )

    # ========================================================
    # SESSION
    # ========================================================

    timeout = aiohttp.ClientTimeout(
        total=15
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={
            "User-Agent": "BOTVOID/1.0"
        }
    ) as session:

        # ====================================================
        # PROCESSAR UM ITEM POR VEZ
        # ====================================================

        for indice, item in enumerate(itens):

            linha = indice // COLUNAS

            coluna = indice % COLUNAS

            x = (
                MARGEM
                + coluna * (
                    CARD_LARGURA
                    + ESPACO
                )
            )

            y = (
                MARGEM
                + altura_cabecalho
                + linha * (
                    CARD_ALTURA
                    + ESPACO
                )
            )

            imagem = None

            url_imagem = obter_imagem_item(
                item
            )

            if url_imagem:

                dados_imagem = await baixar_imagem(
                    session,
                    url_imagem
                )

                if dados_imagem:

                    imagem = preparar_imagem_item(
                        dados_imagem
                    )

                    # Liberar bytes imediatamente
                    del dados_imagem

            # =================================================
            # DESENHAR
            # =================================================

            desenhar_card(
                canvas,
                draw,
                item,
                imagem,
                x,
                y
            )

            # =================================================
            # LIBERAR PIL
            # =================================================

            if imagem:

                try:
                    imagem.close()
                except Exception:
                    pass

                del imagem

            # Pequena pausa para não monopolizar CPU
            if indice % 8 == 0:

                await asyncio.sleep(0)

    # ========================================================
    # SALVAR JPEG
    # ========================================================

    arquivo_memoria = io.BytesIO()

    canvas.save(
        arquivo_memoria,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True
    )

    # Liberar canvas depois da conversão
    canvas.close()

    arquivo_memoria.seek(0)

    print(
        f"[LOJA] Imagem criada: "
        f"{len(arquivo_memoria.getvalue()) / 1024 / 1024:.2f} MB"
    )

    return arquivo_memoria


# ============================================================
# CRIAR EMBED
# ============================================================

def criar_embed():

    embed = discord.Embed(
        title="🛒 Fortnite Item Shop",
        description=(
            "A loja é atualizada automaticamente "
            "quando houver uma mudança."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="BOTVOID • Fortnite Item Shop"
    )

    return embed


# ============================================================
# LOCALIZAR MENSAGEM DA LOJA
# ============================================================

async def localizar_mensagem(canal, message_id):

    if not message_id:
        return None

    try:

        mensagem = await canal.fetch_message(
            int(message_id)
        )

        return mensagem

    except discord.NotFound:

        print(
            "[LOJA] Mensagem antiga não encontrada."
        )

        return None

    except discord.Forbidden:

        print(
            "[ERRO] Sem permissão para acessar "
            "a mensagem da loja."
        )

        return None

    except Exception as erro:

        print(
            f"[ERRO] Buscando mensagem: {erro}"
        )

        return None


# ============================================================
# ATUALIZAR LOJA
# ============================================================

async def atualizar_loja(
    forcar=False
):

    print(
        "[LOJA] Verificando loja..."
    )

    dados = await obter_loja()

    if not dados:

        return

    # ========================================================
    # HASH
    # ========================================================

    shop_hash = dados.get("data", {}).get("hash")

    if not shop_hash:

        print(
            "[AVISO] API não retornou hash."
        )

        # Criar hash alternativo
        try:

            texto = json.dumps(
                dados.get("data", {}),
                sort_keys=True,
                ensure_ascii=False
            )

            import hashlib

            shop_hash = hashlib.sha256(
                texto.encode("utf-8")
            ).hexdigest()

        except Exception:

            shop_hash = str(
                time.time()
            )

    estado = carregar_estado()

    hash_antigo = estado.get(
        "shop_hash"
    )

    message_id = estado.get(
        "message_id"
    )

    # ========================================================
    # NÃO MUDOU
    # ========================================================

    if (
        not forcar
        and hash_antigo == shop_hash
    ):

        print(
            "[LOJA] Nenhuma mudança."
        )

        return

    print(
        "[LOJA] Loja alterada!"
    )

    # ========================================================
    # EXTRAIR ITENS
    # ========================================================

    itens = extrair_itens(
        dados
    )

    if not itens:

        print(
            "[ERRO] Não foi possível encontrar "
            "os itens da loja."
        )

        return

    print(
        f"[LOJA] Encontrados {len(itens)} itens."
    )

    # ========================================================
    # GERAR IMAGEM
    # ========================================================

    try:

        imagem = await criar_imagem_loja(
            itens
        )

    except Exception as erro:

        print(
            f"[ERRO] Gerando imagem: {erro}"
        )

        return

    if not imagem:

        return

    # ========================================================
    # CANAL
    # ========================================================

    canal = bot.get_channel(
        CANAL_LOJA_ID
    )

    if not canal:

        try:

            canal = await bot.fetch_channel(
                CANAL_LOJA_ID
            )

        except Exception as erro:

            print(
                f"[ERRO] Canal da loja não encontrado: {erro}"
            )

            imagem.close()

            return

    # ========================================================
    # ARQUIVO
    # ========================================================

    arquivo = discord.File(
        imagem,
        filename="fortnite-shop.jpg"
    )

    embed = criar_embed()

    # ========================================================
    # PROCURAR MENSAGEM
    # ========================================================

    mensagem = await localizar_mensagem(
        canal,
        message_id
    )

    # ========================================================
    # EDITAR EXISTENTE
    # ========================================================

    if mensagem:

        try:

            await mensagem.edit(
                content=None,
                embed=embed,
                attachments=[
                    arquivo
                ]
            )

            salvar_estado(
                shop_hash,
                mensagem.id
            )

            print(
                "[LOJA] Mensagem atualizada."
            )

            return

        except Exception as erro:

            print(
                f"[ERRO] Editando mensagem: {erro}"
            )

    # ========================================================
    # CRIAR NOVA
    # ========================================================

    try:

        mensagem = await canal.send(
            embed=embed,
            file=arquivo
        )

        salvar_estado(
            shop_hash,
            mensagem.id
        )

        print(
            "[LOJA] Nova mensagem criada."
        )

    except Exception as erro:

        print(
            f"[ERRO] Enviando loja: {erro}"
        )


# ============================================================
# LOOP DA LOJA
# ============================================================

@tasks.loop(
    seconds=INTERVALO_VERIFICACAO
)
async def verificar_loja():

    try:

        await atualizar_loja()

    except Exception as erro:

        print(
            f"[ERRO] Loop da loja: {erro}"
        )


# ============================================================
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        "========================================"
    )

    print(
        f"BOT ONLINE: {bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Atualização inicial
    # --------------------------------------------------------

    try:

        await atualizar_loja()

    except Exception as erro:

        print(
            f"[ERRO] Atualização inicial: {erro}"
        )

    # --------------------------------------------------------
    # Iniciar loop
    # --------------------------------------------------------

    if not verificar_loja.is_running():

        verificar_loja.start()

        print(
            "[LOJA] Monitoramento iniciado."
        )


# ============================================================
# SISTEMA DE REAÇÕES
# ============================================================

@bot.event
async def on_message(message):

    # Ignorar mensagens de bots
    if message.author.bot:
        return

    # ========================================================
    # CANAL ESPECÍFICO
    # ========================================================

    if message.channel.id == CANAL_REACOES_ID:

        try:

            await message.add_reaction("🟢")

            await message.add_reaction("⚖️")

            await message.add_reaction("🔴")

            print(
                f"[REAÇÕES] Reações adicionadas "
                f"em {message.author}"
            )

        except Exception as erro:

            print(
                f"[ERRO] Adicionando reações: {erro}"
            )

    # ========================================================
    # COMANDOS
    # ========================================================

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
        "🔄 Gerando teste da loja..."
    )

    try:

        await atualizar_loja(
            forcar=True
        )

        await mensagem.edit(
            content="✅ Loja atualizada!"
        )

    except Exception as erro:

        await mensagem.edit(
            content=f"❌ Erro: `{erro}`"
        )


# ============================================================
# ERRO DE PERMISSÃO
# ============================================================

@teste_loja.error
async def teste_loja_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ Você precisa ser administrador."
        )


# ============================================================
# VERIFICAÇÃO DE CONFIGURAÇÃO
# ============================================================

if not TOKEN:

    print(
        "========================================"
    )

    print(
        "ERRO: DISCORD_TOKEN não foi encontrado."
    )

    print(
        "Configure a variável de ambiente:"
    )

    print(
        "DISCORD_TOKEN"
    )

    print(
        "========================================"

    )

else:

    bot.run(TOKEN)