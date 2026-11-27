"""Imagem do versículo do dia para partilha no Facebook e no Instagram.

Formato 1080x1350 px (4:5, retrato): é o maior formato que o feed do
Instagram mostra sem cortes e o Facebook mostra-o inteiro no feed. As
margens laterais (>= 100 px) protegem o texto do corte 3:4 da grelha do
perfil do Instagram. JPEG sRGB, qualidade 95, sem subamostragem de cor
(texto nítido mesmo depois da recompressão das redes sociais).

Sem hashtags: só o versículo, a referência e a versão bíblica.
Fontes: Lora e Montserrat (SIL Open Font License, ver fontes/OFL-*.txt).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LARGURA, ALTURA = 1080, 1350
MARGEM_X = 110
LARGURA_TEXTO = LARGURA - 2 * MARGEM_X

# Zona útil do bloco central (versículo + referência), entre o cabeçalho e o rodapé.
TOPO_BLOCO, BASE_BLOCO = 250, 1160
TAMANHO_MAX, TAMANHO_MIN = 76, 30
ESPACAMENTO_LINHAS = 1.38
# Alturas fixas do bloco central: aspas, intervalo, intervalo antes da
# referência, referência, intervalo, nome da versão.
ALTURA_ASPAS, GAP_ASPAS = 90, 10
GAP_REF, ALTURA_REF, GAP_VERSAO, ALTURA_VERSAO = 56, 48, 12, 34
ALTURA_FIXA = ALTURA_ASPAS + GAP_ASPAS + GAP_REF + ALTURA_REF + GAP_VERSAO + ALTURA_VERSAO
ALTURA_TEXTO_MAX = BASE_BLOCO - TOPO_BLOCO - ALTURA_FIXA

COR_FUNDO_TOPO = (13, 35, 58)       # azul-noite
COR_FUNDO_BASE = (24, 82, 96)       # azul-petróleo
COR_TEXTO = (250, 247, 240)
COR_DESTAQUE = (232, 199, 122)      # dourado
COR_SUAVE = (250, 247, 240, 165)

PASTA_FONTES = Path(__file__).with_name("fontes")
RODAPE_PADRAO = "IASD Angra do Heroísmo"


def _fonte(ficheiro: str, tamanho: int, variacao: str | None = None) -> ImageFont.FreeTypeFont:
    fonte = ImageFont.truetype(str(PASTA_FONTES / ficheiro), tamanho)
    if variacao:
        fonte.set_variation_by_name(variacao)
    return fonte


def _fundo() -> Image.Image:
    """Gradiente vertical com um brilho suave no topo."""
    topo = Image.new("RGB", (1, 2), 0)
    topo.putpixel((0, 0), COR_FUNDO_TOPO)
    topo.putpixel((0, 1), COR_FUNDO_BASE)
    img = topo.resize((LARGURA, ALTURA), Image.Resampling.BILINEAR)

    brilho = Image.new("L", (LARGURA, ALTURA), 0)
    ImageDraw.Draw(brilho).ellipse((-100, -500, LARGURA + 100, 380), fill=34)
    brilho = brilho.filter(ImageFilter.GaussianBlur(180))
    return Image.composite(Image.new("RGB", img.size, (255, 255, 255)), img, brilho)


def _quebrar_linhas(texto: str, fonte: ImageFont.FreeTypeFont, largura: int) -> list[str]:
    """Quebra gulosa por palavras, medida com a fonte real."""
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if not atual or fonte.getlength(tentativa) <= largura:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _ajustar_texto(texto: str, altura_disponivel: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Maior tamanho de letra (TAMANHO_MAX..TAMANHO_MIN) em que o texto cabe."""
    for tamanho in range(TAMANHO_MAX, TAMANHO_MIN - 1, -2):
        fonte = _fonte("Lora-Italic-VF.ttf", tamanho)
        linhas = _quebrar_linhas(texto, fonte, LARGURA_TEXTO)
        altura_linha = round(tamanho * ESPACAMENTO_LINHAS)
        if len(linhas) * altura_linha <= altura_disponivel:
            return fonte, linhas, altura_linha
    raise ValueError(f"Versículo demasiado longo para a imagem ({len(texto)} caracteres).")


def _centrado(desenho: ImageDraw.ImageDraw, y: int, texto: str,
              fonte: ImageFont.FreeTypeFont, cor: tuple[int, ...], espacamento: int = 0) -> None:
    if not espacamento:
        desenho.text((LARGURA // 2, y), texto, font=fonte, fill=cor, anchor="mt")
        return
    # Letras espaçadas (rótulos em maiúsculas). Âncora na linha de base
    # ("ls"): com "lt" as letras acentuadas (Í) desciam para alinhar o acento.
    larguras = [fonte.getlength(c) for c in texto]
    x = (LARGURA - (sum(larguras) + espacamento * (len(texto) - 1))) / 2
    base = y + fonte.getmetrics()[0]
    for c, w in zip(texto, larguras):
        desenho.text((x, base), c, font=fonte, fill=cor, anchor="ls")
        x += w + espacamento


def gerar_imagem(referencia: str, texto: str, destino: Path,
                 rodape: str = RODAPE_PADRAO) -> Path:
    """Desenha o versículo e grava-o em 'destino' (JPEG). Devolve o caminho."""
    texto = " ".join(texto.split())
    # Alguns versículos são excertos que começam em minúscula ("tudo posso…").
    texto = texto[:1].upper() + texto[1:]
    img = _fundo().convert("RGBA")
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    # Cabeçalho
    _centrado(d, 128, "VERSÍCULO DO DIA", _fonte("Montserrat-VF.ttf", 30, "SemiBold"),
              COR_DESTAQUE, espacamento=6)
    d.line((LARGURA // 2 - 60, 186, LARGURA // 2 + 60, 186), fill=COR_DESTAQUE, width=3)

    # Bloco central: aspas decorativas + versículo + referência, centrado na zona útil.
    fonte_aspas = _fonte("Lora-VF.ttf", 150, "Bold")
    fonte_ref = _fonte("Montserrat-VF.ttf", 40, "Bold")
    fonte_versao = _fonte("Montserrat-VF.ttf", 26, "Medium")
    fonte_txt, linhas, altura_linha = _ajustar_texto(texto, ALTURA_TEXTO_MAX)
    altura_bloco = ALTURA_FIXA + len(linhas) * altura_linha
    y = TOPO_BLOCO + (BASE_BLOCO - TOPO_BLOCO - altura_bloco) // 2

    d.text((LARGURA // 2, y - 10), "“", font=fonte_aspas, fill=COR_DESTAQUE + (150,), anchor="mt")
    y += ALTURA_ASPAS + GAP_ASPAS
    for linha in linhas:
        d.text((LARGURA // 2, y), linha, font=fonte_txt, fill=COR_TEXTO, anchor="mt")
        y += altura_linha
    y += GAP_REF
    _centrado(d, y, referencia, fonte_ref, COR_DESTAQUE)
    y += ALTURA_REF + GAP_VERSAO
    _centrado(d, y, "Almeida Revista e Atualizada", fonte_versao, COR_SUAVE)

    # Rodapé
    if rodape:
        d.line((MARGEM_X, 1218, LARGURA - MARGEM_X, 1218), fill=(250, 247, 240, 60), width=1)
        _centrado(d, 1248, rodape, _fonte("Montserrat-VF.ttf", 26, "Medium"), COR_SUAVE)

    final = Image.alpha_composite(img, camada).convert("RGB")
    destino.parent.mkdir(parents=True, exist_ok=True)
    final.save(destino, "JPEG", quality=95, subsampling=0, optimize=True)
    return destino
