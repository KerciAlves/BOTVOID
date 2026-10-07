import discord
from discord.ext import commands, tasks

import aiohttp
import asyncio
import io
import json
import os
import hashlib
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# Canal onde continuam funcionando as reações
CANAL_REACOES_ID = 1556998399461691443

# Canal da Loja Fortnite
CANAL_LOJA_ID = 1214658145243234324

FORTNITE_SHOP_URL = "https://fortnite-api.com/v2/shop"

IDIOMA = "pt-BR"

INTERVALO_VERIFICACAO = 5

SHOP_STATE_FILE = "shop_state.json"

ITENS_POR_PAGINA = 4


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

pagina_atual = 0


# ============================================================
# FONTES
# ============================================================

def carregar_fonte(tamanho, negrito=False):

    caminhos = []

    if negrito:
        caminhos = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
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


# ============================================================
# ESTADO DO BOT
# ============================================================

def carregar_estado():

    global ultima_loja_hash
    global mensagem_loja_id

    if not os.path.exists(SHOP_STATE_FILE):
        return

    try:

        with open(SHOP_STATE_FILE, "r", encoding="utf-8") as arquivo:
            estado = json.load(arquivo)

        ultima_loja_hash = estado.get("shop_hash")
        mensagem_loja_id = estado.get("message_id")

        print("Estado da loja carregado.")

    except Exception as erro:

        print(f"Erro ao carregar estado: {erro}")


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

        print(f"Erro ao salvar estado: {erro}")


# ============================================================
# API FORTNITE
# ============================================================

async def buscar_loja():

    try:

        timeout = aiohttp.ClientTimeout(total=30)

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
                        f"API retornou HTTP {resposta.status}"
                    )

                    return None

                return await resposta.json()

    except Exception as erro:

        print(f"Erro ao consultar Fortnite API: {erro}")

        return None


# ============================================================
# UTILIDADES
# ============================================================

def primeiro_valor(dicionario, *chaves, padrao=None):

    if not isinstance(dicionario, dict):
        return padrao

    for chave in chaves:

        valor = dicionario.get(chave)

        if valor is not None:
            return valor

    return padrao


def obter_imagem(item):

    if not isinstance(item, dict):
        return None

    imagens = item.get("images")

    if isinstance(imagens, dict):

        for chave in [
            "featured",
            "icon",
            "background",
            "full_background",
            "other"
        ]:

            valor = imagens.get(chave)

            if isinstance(valor, str) and valor.startswith("http"):
                return valor

    for chave in [
        "image",
        "icon",
        "iconUrl"
    ]:

        valor = item.get(chave)

        if isinstance(valor, str) and valor.startswith("http"):
            return valor

    return None


def obter_nome(item):

    return primeiro_valor(
        item,
        "name",
        "title",
        "displayName",
        padrao="Item desconhecido"
    )


def obter_tipo(item):

    tipo = item.get("type")

    if isinstance(tipo, dict):

        return primeiro_valor(
            tipo,
            "displayValue",
            "value",
            "name",
            padrao="Item"
        )

    return (
        item.get("displayType")
        or item.get("type")
        or "Item"
    )


def obter_raridade(item):

    raridade = item.get("rarity")

    if isinstance(raridade, dict):

        return primeiro_valor(
            raridade,
            "displayValue",
            "value",
            "name",
            padrao=""
        )

    return (
        item.get("displayRarity")
        or item.get("rarity")
        or ""
    )


def obter_preco(entry):

    if not isinstance(entry, dict):
        return None

    preco = primeiro_valor(
        entry,
        "finalPrice",
        "final_price",
        "regularPrice",
        "regular_price",
        "price"
    )

    if isinstance(preco, dict):

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

    # Alguns formatos podem guardar o preço dentro de um bundle
    bundle = entry.get("bundle")

    if isinstance(bundle, dict):

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
        return "PREÇO N/D"

    return f"{preco:,}".replace(",", ".") + " V-BUCKS"


# ============================================================
# EXTRAÇÃO DOS ITENS
# ============================================================

def extrair_itens(loja):

    if not isinstance(loja, dict):
        return []

    data = loja.get("data", loja)

    if not isinstance(data, dict):
        return []

    entries = data.get("entries", [])

    if not isinstance(entries, list):
        return []

    resultado = []

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        preco = obter_preco(entry)

        # Possíveis coleções usadas pela API
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

        for nome_colecao in colecoes:

            valor = entry.get(nome_colecao)

            if isinstance(valor, list):
                encontrados.extend(valor)

        # Caso seja uma entrada diretamente com dados do item
        if not encontrados:

            if (
                entry.get("name")
                or entry.get("displayName")
                or entry.get("images")
            ):
                encontrados.append(entry)

        for item in encontrados:

            if not isinstance(item, dict):
                continue

            imagem = obter_imagem(item)

            if not imagem:
                continue

            nome = obter_nome(item)

            raridade = obter_raridade(item)

            tipo = obter_tipo(item)

            resultado.append({
                "name": nome,
                "image": imagem,
                "rarity": raridade,
                "type": tipo,
                "price": preco
            })

    # Remove duplicados
    unicos = []

    ids = set()

    for item in resultado:

        identificador = (
            item["name"],
            item["image"],
            item["price"]
        )

        if identificador in ids:
            continue

        ids.add(identificador)
        unicos.append(item)

    return unicos


# ============================================================
# COR DA RARIDADE
# ============================================================

def cor_raridade(raridade):

    texto = str(raridade).lower()

    if "legend" in texto:
        return (255, 190, 55)

    if "epic" in texto:
        return (190, 70, 255)

    if "rare" in texto:
        return (50, 150, 255)

    if "uncommon" in texto:
        return (70, 200, 110)

    if "marvel" in texto:
        return (220, 50, 70)

    if "star wars" in texto:
        return (70, 130, 220)

    if "gaming" in texto:
        return (100, 180, 255)

    return (100, 110, 130)


# ============================================================
# DOWNLOAD DE IMAGEM
# ============================================================

async def baixar_imagem(session, url):

    try:

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as resposta:

            if resposta.status != 200:
                return None

            dados = await resposta.read()

            imagem = Image.open(
                io.BytesIO(dados)
            ).convert("RGB")

            return imagem

    except Exception as erro:

        print(
            f"Erro baixando imagem {url}: {erro}"
        )

        return None


# ============================================================
# AJUSTAR IMAGEM
# ============================================================

def preencher_imagem(imagem, tamanho):

    largura, altura = tamanho

    if imagem is None:

        return Image.new(
            "RGB",
            tamanho,
            (35, 40, 50)
        )

    proporcao_original = (
        imagem.width / imagem.height
    )

    proporcao_destino = (
        largura / altura
    )

    if proporcao_original > proporcao_destino:

        nova_altura = altura

        nova_largura = int(
            altura * proporcao_original
        )

    else:

        nova_largura = largura

        nova_altura = int(
            largura / proporcao_original
        )

    imagem = imagem.resize(
        (nova_largura, nova_altura),
        Image.Resampling.LANCZOS
    )

    esquerda = (
        nova_largura - largura
    ) // 2

    topo = (
        nova_altura - altura
    ) // 2

    imagem = imagem.crop(
        (
            esquerda,
            topo,
            esquerda + largura,
            topo + altura
        )
    )

    return imagem


# ============================================================
# TEXTO COM RETICÊNCIAS
# ============================================================

def texto_limitado(draw, texto, fonte, largura):

    if draw.textbbox(
        (0, 0),
        texto,
        font=fonte
    )[2] <= largura:

        return texto

    while len(texto) > 3:

        texto = texto[:-1]

        teste = texto + "..."

        if draw.textbbox(
            (0, 0),
            teste,
            font=fonte
        )[2] <= largura:

            return teste

    return "..."


# ============================================================
# DESENHAR CARD
# ============================================================

def desenhar_card(
    canvas,
    item,
    imagem,
    x,
    y,
    largura,
    altura
):

    draw = ImageDraw.Draw(canvas)

    # Fundo
    draw.rounded_rectangle(
        (
            x,
            y,
            x + largura,
            y + altura
        ),
        radius=18,
        fill=(24, 27, 36),
        outline=(70, 76, 92),
        width=2
    )

    # Cor da raridade
    cor = cor_raridade(
        item.get("rarity", "")
    )

    # Área da imagem
    margem = 8

    area_imagem = (
        largura - margem * 2,
        altura - 105
    )

    imagem = preencher_imagem(
        imagem,
        area_imagem
    )

    canvas.paste(
        imagem,
        (
            x + margem,
            y + margem
        )
    )

    # Faixa da raridade
    draw.rectangle(
        (
            x + margem,
            y + margem,
            x + largura - margem,
            y + margem + 7
        ),
        fill=cor
    )

    fonte_nome = carregar_fonte(
        22,
        negrito=True
    )

    fonte_tipo = carregar_fonte(
        15
    )

    fonte_preco = carregar_fonte(
        18,
        negrito=True
    )

    nome = texto_limitado(
        draw,
        str(item.get("name", "Item")),
        fonte_nome,
        largura - 30
    )

    draw.text(
        (
            x + 15,
            y + altura - 91
        ),
        nome,
        fill=(255, 255, 255),
        font=fonte_nome
    )

    tipo = str(
        item.get("type", "Item")
    )

    draw.text(
        (
            x + 15,
            y + altura - 61
        ),
        tipo,
        fill=(170, 176, 190),
        font=fonte_tipo
    )

    preco = formatar_preco(
        item.get("price")
    )

    # Preço
    draw.text(
        (
            x + 15,
            y + altura - 37
        ),
        "●  " + preco,
        fill=(255, 255, 255),
        font=fonte_preco
    )


# ============================================================
# CRIAR IMAGEM DA PÁGINA
# ============================================================

async def criar_imagem_loja(
    itens,
    pagina,
    total_paginas,
    data_loja
):

    LARGURA = 1200
    ALTURA = 930

    canvas = Image.new(
        "RGB",
        (LARGURA, ALTURA),
        (12, 14, 20)
    )

    draw = ImageDraw.Draw(canvas)

    # Fundo com gradiente simples
    for y in range(ALTURA):

        fator = y / ALTURA

        r = int(12 + fator * 8)
        g = int(14 + fator * 12)
        b = int(20 + fator * 20)

        draw.line(
            (
                0,
                y,
                LARGURA,
                y
            ),
            fill=(r, g, b)
        )

    # Título
    fonte_titulo = carregar_fonte(
        38,
        negrito=True
    )

    fonte_subtitulo = carregar_fonte(
        17
    )

    draw.text(
        (40, 25),
        "LOJA DE ITENS",
        fill=(255, 255, 255),
        font=fonte_titulo
    )

    draw.text(
        (42, 72),
        "FORTNITE • ATUALIZAÇÃO AUTOMÁTICA",
        fill=(150, 160, 180),
        font=fonte_subtitulo
    )

    # Data
    if data_loja:

        try:

            data_formatada = (
                datetime.fromisoformat(
                    data_loja.replace(
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

        data_formatada = "Agora"

    draw.text(
        (850, 48),
        data_formatada,
        fill=(180, 185, 200),
        font=fonte_subtitulo
    )

    # Linha decorativa
    draw.line(
        (40, 105, 1160, 105),
        fill=(55, 62, 78),
        width=2
    )

    # Itens da página
    inicio = pagina * ITENS_POR_PAGINA

    itens_pagina = itens[
        inicio:
        inicio + ITENS_POR_PAGINA
    ]

    # Dimensões dos cards
    card_largura = 545
    card_altura = 370

    posicoes = [
        (40, 130),
        (615, 130),
        (40, 520),
        (615, 520)
    ]

    async with aiohttp.ClientSession() as session:

        tarefas = []

        for item in itens_pagina:

            tarefas.append(
                baixar_imagem(
                    session,
                    item["image"]
                )
            )

        imagens = await asyncio.gather(
            *tarefas,
            return_exceptions=True
        )

    for indice, item in enumerate(itens_pagina):

        imagem = imagens[indice]

        if isinstance(
            imagem,
            Exception
        ):

            imagem = None

        x, y = posicoes[indice]

        desenhar_card(
            canvas,
            item,
            imagem,
            x,
            y,
            card_largura,
            card_altura
        )

    # Cards vazios
    for indice in range(
        len(itens_pagina),
        4
    ):

        x, y = posicoes[indice]

        draw.rounded_rectangle(
            (
                x,
                y,
                x + card_largura,
                y + card_altura
            ),
            radius=18,
            fill=(20, 23, 30),
            outline=(45, 50, 62),
            width=2
        )

        fonte = carregar_fonte(
            20,
            negrito=True
        )

        texto = "SEM ITEM"

        caixa = draw.textbbox(
            (0, 0),
            texto,
            font=fonte
        )

        tx = x + (
            card_largura -
            (caixa[2] - caixa[0])
        ) / 2

        ty = y + (
            card_altura -
            (caixa[3] - caixa[1])
        ) / 2

        draw.text(
            (tx, ty),
            texto,
            fill=(80, 85, 100),
            font=fonte
        )

    # Rodapé
    fonte_rodape = carregar_fonte(
        17
    )

    texto_rodape = (
        f"Página {pagina + 1}/{total_paginas}  •  "
        f"{len(itens)} itens encontrados"
    )

    caixa = draw.textbbox(
        (0, 0),
        texto_rodape,
        font=fonte_rodape
    )

    draw.text(
        (
            (LARGURA - (caixa[2] - caixa[0])) / 2,
            895
        ),
        texto_rodape,
        fill=(150, 155, 170),
        font=fonte_rodape
    )

    # Salvar na memória
    buffer = io.BytesIO()

    canvas.save(
        buffer,
        format="PNG",
        optimize=True
    )

    buffer.seek(0)

    return buffer


# ============================================================
# HASH DA LOJA
# ============================================================

def obter_hash_loja(loja):

    if not isinstance(loja, dict):
        return None

    data = loja.get("data", loja)

    if not isinstance(data, dict):
        return None

    shop_hash = data.get("hash")

    if shop_hash:
        return str(shop_hash)

    # Fallback caso a API não envie hash
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
            texto.encode("utf-8")
        ).hexdigest()

    except Exception:

        return None


def obter_data_loja(loja):

    if not isinstance(loja, dict):
        return None

    data = loja.get("data", loja)

    if not isinstance(data, dict):
        return None

    return (
        data.get("date")
        or data.get("lastUpdate")
        or data.get("last_update")
    )


# ============================================================
# VIEW DOS BOTÕES
# ============================================================

class LojaView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="◀️",
        style=discord.ButtonStyle.secondary,
        custom_id="loja_anterior"
    )
    async def anterior(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        global pagina_atual

        total_paginas = max(
            1,
            (
                len(loja_atual)
                + ITENS_POR_PAGINA
                - 1
            ) // ITENS_POR_PAGINA
        )

        pagina_atual -= 1

        if pagina_atual < 0:
            pagina_atual = total_paginas - 1

        await atualizar_pagina(
            interaction
        )

    @discord.ui.button(
        label="🔄",
        style=discord.ButtonStyle.primary,
        custom_id="loja_atualizar"
    )
    async def atualizar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.defer()

        await verificar_loja(
            forcar=True
        )

        # Se não houve alteração, ainda atualizamos a página
        try:

            await interaction.message.edit(
                attachments=[],
                embed=await criar_embed_pagina()
            )

            arquivo = await criar_arquivo_pagina()

            embed = await criar_embed_pagina()

            await interaction.message.edit(
                embed=embed,
                attachments=[
                    arquivo
                ],
                view=LojaView()
            )

        except Exception as erro:

            print(
                f"Erro ao atualizar botão: {erro}"
            )

    @discord.ui.button(
        label="▶️",
        style=discord.ButtonStyle.secondary,
        custom_id="loja_proxima"
    )
    async def proximo(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        global pagina_atual

        total_paginas = max(
            1,
            (
                len(loja_atual)
                + ITENS_POR_PAGINA
                - 1
            ) // ITENS_POR_PAGINA
        )

        pagina_atual += 1

        if pagina_atual >= total_paginas:
            pagina_atual = 0

        await atualizar_pagina(
            interaction
        )


# ============================================================
# GERAR ARQUIVO DA PÁGINA
# ============================================================

async def criar_arquivo_pagina():

    total_paginas = max(
        1,
        (
            len(loja_atual)
            + ITENS_POR_PAGINA
            - 1
        ) // ITENS_POR_PAGINA
    )

    imagem = await criar_imagem_loja(
        loja_atual,
        pagina_atual,
        total_paginas,
        loja_data
    )

    return discord.File(
        imagem,
        filename="fortnite_shop.png"
    )


# ============================================================
# EMBED DA PÁGINA
# ============================================================

async def criar_embed_pagina():

    total_paginas = max(
        1,
        (
            len(loja_atual)
            + ITENS_POR_PAGINA
            - 1
        ) // ITENS_POR_PAGINA
    )

    embed = discord.Embed(
        color=discord.Color.from_rgb(
            45,
            110,
            220
        )
    )

    embed.set_image(
        url="attachment://fortnite_shop.png"
    )

    embed.set_footer(
        text=(
            f"Página {pagina_atual + 1}/{total_paginas} "
            f"• Atualizado automaticamente"
        )
    )

    return embed


# ============================================================
# ATUALIZAR PÁGINA
# ============================================================

async def atualizar_pagina(
    interaction
):

    try:

        await interaction.response.defer()

        arquivo = await criar_arquivo_pagina()

        embed = await criar_embed_pagina()

        await interaction.message.edit(
            embed=embed,
            attachments=[
                arquivo
            ],
            view=LojaView()
        )

    except Exception as erro:

        print(
            f"Erro ao mudar página: {erro}"
        )


# ============================================================
# ATUALIZAR MENSAGEM DA LOJA
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
                f"Não consegui acessar o canal da loja: {erro}"
            )

            return

    arquivo = await criar_arquivo_pagina()

    embed = await criar_embed_pagina()

    view = LojaView()

    mensagem = None

    # Tentar encontrar mensagem existente
    if mensagem_loja_id:

        try:

            mensagem = await canal.fetch_message(
                int(mensagem_loja_id)
            )

        except Exception:

            mensagem = None

    # Se não encontrou, procura mensagens recentes do bot
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
                f"Erro procurando mensagem antiga: {erro}"
            )

    # Editar mensagem existente
    if mensagem:

        try:

            await mensagem.edit(
                embed=embed,
                attachments=[
                    arquivo
                ],
                view=view
            )

        except Exception as erro:

            print(
                f"Erro editando mensagem: {erro}"
            )

            try:

                mensagem = await canal.send(
                    embed=embed,
                    file=arquivo,
                    view=view
                )

                mensagem_loja_id = mensagem.id

            except Exception as erro2:

                print(
                    f"Erro criando nova mensagem: {erro2}"
                )

    else:

        try:

            mensagem = await canal.send(
                embed=embed,
                file=arquivo,
                view=view
            )

            mensagem_loja_id = mensagem.id

        except Exception as erro:

            print(
                f"Erro enviando loja: {erro}"
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
    global pagina_atual

    loja = await buscar_loja()

    if loja is None:
        return False

    novo_hash = obter_hash_loja(
        loja
    )

    if not novo_hash:

        print(
            "Não foi possível identificar a loja."
        )

        return False

    mudou = (
        novo_hash != ultima_loja_hash
    )

    if not mudou and not forcar:

        return False

    itens = extrair_itens(
        loja
    )

    if not itens:

        print(
            "A API retornou a loja, mas nenhum item foi encontrado."
        )

        return False

    loja_atual = itens

    loja_data = obter_data_loja(
        loja
    )

    ultima_loja_hash = novo_hash

    # Sempre começa na primeira página quando a loja muda
    if mudou:

        pagina_atual = 0

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
# LOOP AUTOMÁTICO
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
async def antes_verificar_loja():

    await bot.wait_until_ready()


# ============================================================
# EVENTO READY
# ============================================================

@bot.event
async def on_ready():

    global loja_atual

    print(
        f"Bot conectado como {bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    carregar_estado()

    # Evita iniciar o loop duas vezes
    if not verificar_loja_loop.is_running():

        verificar_loja_loop.start()

    # Primeira consulta
    await verificar_loja()


# ============================================================
# REAÇÕES
# ============================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # NÃO ALTERADO
    # Canal original das reações
    if message.channel.id == CANAL_REACOES_ID:

        try:

            await message.add_reaction("🟢")
            await message.add_reaction("⚖️")
            await message.add_reaction("🔴")

        except Exception as erro:

            print(
                f"Erro adicionando reações: {erro}"
            )

    await bot.process_commands(
        message
    )


# ============================================================
# COMANDO TESTE
# ============================================================

@bot.command(
    name="testeloja"
)
@commands.has_permissions(
    administrator=True
)
async def teste_loja(ctx):

    await ctx.send(
        "🔄 Atualizando a Loja Fortnite..."
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
# TRATAMENTO DE ERRO
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
# INICIAR BOT
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi configurada."
    )


bot.run(TOKEN)