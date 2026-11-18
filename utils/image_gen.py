"""
utils/image_gen.py
---------------------
Génère dynamiquement une image façon "avis de recherche" (Wanted Poster)
pour le /profile, avec l'avatar du membre découpé en rond.

Tout est dessiné à la volée avec Pillow (aucune image externe utilisée,
donc aucun souci de droits d'auteur) : fond "papier vieilli" généré par
code, cadre décoratif, texte "WANTED", avatar circulaire avec anneau doré,
tampon de prime, etc.
"""

import io
import os
import random

import discord
from PIL import Image, ImageDraw, ImageFont, ImageChops

# --- Dimensions de l'affiche ---
WIDTH, HEIGHT = 640, 880

# --- Palette "papier vieilli" ---
PAPER_COLOR = (231, 209, 168)
INK_DARK = (46, 30, 18)
INK_RED = (139, 24, 24)
GOLD_RING = (150, 108, 34)
MUTED_BROWN = (120, 96, 66)

# --- Recherche de polices disponibles (Windows / Linux / macOS) ---
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CUSTOM_FONT_DIR = os.path.join(_BASE_DIR, "assets", "fonts")

_BOLD_CANDIDATES = [
    os.path.join(_CUSTOM_FONT_DIR, "pirate_bold.ttf"),  # dépose ta propre police ici si tu veux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\Arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

_REGULAR_CANDIDATES = [
    os.path.join(_CUSTOM_FONT_DIR, "pirate_regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    """Essaie chaque police de la liste dans l'ordre, sinon retombe sur la police par défaut de Pillow."""
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fit_font(text: str, candidates: list[str], max_width: int, start_size: int, min_size: int = 14):
    """Réduit progressivement la taille de police jusqu'à ce que le texte tienne dans max_width."""
    size = start_size
    while size > min_size:
        font = _load_font(candidates, size)
        # getlength existe sur les fontes truetype modernes de Pillow
        try:
            width = font.getlength(text)
        except AttributeError:
            width = font.getsize(text)[0]
        if width <= max_width:
            return font
        size -= 2
    return _load_font(candidates, min_size)


def _add_paper_texture(base: Image.Image) -> Image.Image:
    """Ajoute un léger grain façon vieux papier, généré procéduralement (pas d'image externe)."""
    w, h = base.size
    small_w, small_h = max(1, w // 6), max(1, h // 6)
    noise_bytes = bytes(random.randint(215, 255) for _ in range(small_w * small_h))
    noise = Image.frombytes("L", (small_w, small_h), noise_bytes)
    noise = noise.resize((w, h), Image.BILINEAR).convert("RGB")
    return ImageChops.multiply(base, noise)


def _draw_frame(draw: ImageDraw.ImageDraw):
    """Dessine un cadre décoratif façon vieille affiche (plusieurs liserés imbriqués)."""
    layers = [
        (0, INK_DARK),
        (6, MUTED_BROWN),
        (10, INK_DARK),
    ]
    for offset, color in layers:
        draw.rectangle(
            [offset, offset, WIDTH - 1 - offset, HEIGHT - 1 - offset],
            outline=color,
            width=3,
        )


def _make_circular_avatar(avatar_bytes: bytes, diameter: int) -> Image.Image:
    """Découpe l'avatar du membre en cercle parfait, avec anti-aliasing (supersampling)."""
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

    # On travaille en résolution 4x puis on réduit, pour un cercle bien lisse
    supersample = diameter * 4
    avatar = avatar.resize((supersample, supersample), Image.LANCZOS)

    mask = Image.new("L", (supersample, supersample), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, supersample, supersample], fill=255)

    circular = Image.new("RGBA", (supersample, supersample), (0, 0, 0, 0))
    circular.paste(avatar, (0, 0), mask=mask)
    circular = circular.resize((diameter, diameter), Image.LANCZOS)

    return circular


def _draw_centered_text(base: Image.Image, text: str, y: int, font: ImageFont.FreeTypeFont, color):
    draw = ImageDraw.Draw(base)
    try:
        width = draw.textlength(text, font=font)
    except AttributeError:
        width = font.getsize(text)[0]
    x = (WIDTH - width) / 2
    draw.text((x, y), text, font=font, fill=color)


def _rotated_text(text: str, font: ImageFont.FreeTypeFont, color, angle: float) -> Image.Image:
    """Rend un texte sur un calque transparent puis le fait pivoter (effet tampon/étiquette)."""
    dummy = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy)
    bbox = dummy_draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0] + 10, bbox[3] - bbox[1] + 10

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.text((5, 5), text, font=font, fill=color)
    return layer.rotate(angle, expand=True, resample=Image.BICUBIC)


def generate_wanted_poster_sync(
    avatar_bytes: bytes,
    display_name: str,
    fleet_and_title: str,
    bounty: int,
) -> io.BytesIO:
    """
    Construit l'image de l'avis de recherche et la retourne sous forme de
    buffer PNG en mémoire. Fonction synchrone (le calcul d'image ne dépend
    d'aucun appel réseau), pensée pour être appelée via generate_wanted_poster().
    """
    base = Image.new("RGB", (WIDTH, HEIGHT), PAPER_COLOR)
    base = _add_paper_texture(base)
    draw = ImageDraw.Draw(base)

    _draw_frame(draw)

    # --- "WANTED" en haut, légèrement penché comme un tampon officiel ---
    wanted_font = _load_font(_BOLD_CANDIDATES, 88)
    wanted_layer = _rotated_text("WANTED", wanted_font, INK_DARK, angle=-2)
    base.paste(
        wanted_layer,
        (int((WIDTH - wanted_layer.width) / 2), 35),
        wanted_layer,
    )

    # --- Avatar circulaire avec anneau doré ---
    diameter = 300
    avatar_circle = _make_circular_avatar(avatar_bytes, diameter)
    avatar_x = int((WIDTH - diameter) / 2)
    avatar_y = 165

    ring_padding = 10
    draw.ellipse(
        [
            avatar_x - ring_padding,
            avatar_y - ring_padding,
            avatar_x + diameter + ring_padding,
            avatar_y + diameter + ring_padding,
        ],
        outline=GOLD_RING,
        width=8,
    )
    base.paste(avatar_circle, (avatar_x, avatar_y), avatar_circle)

    ring_bottom = avatar_y + diameter + ring_padding  # bas de l'anneau doré

    # --- Nom du membre ---
    name_font = _fit_font(display_name, _BOLD_CANDIDATES, WIDTH - 80, 42)
    name_y = ring_bottom + 20
    _draw_centered_text(base, display_name, name_y, name_font, INK_DARK)

    # --- Flotte | Titre ---
    subtitle_font = _fit_font(fleet_and_title, _REGULAR_CANDIDATES, WIDTH - 60, 26)
    subtitle_y = name_y + 62
    _draw_centered_text(base, fleet_and_title, subtitle_y, subtitle_font, MUTED_BROWN)

    # --- Tampon de prime ---
    # On évite le symbole ฿ dans l'image : de nombreuses polices système
    # (notamment Arial sur Windows) ne contiennent pas ce glyphe Thaï et
    # affichent un carré vide à la place. "Berrys" fonctionne avec n'importe
    # quelle police, sur n'importe quel OS.
    bounty_display = f"{bounty:,}".replace(",", " ")
    bounty_text = f"PRIME : {bounty_display} Berrys"
    bounty_font = _fit_font(bounty_text, _BOLD_CANDIDATES, WIDTH - 60, 40)
    bounty_y = subtitle_y + 55
    _draw_centered_text(base, bounty_text, bounty_y, bounty_font, INK_RED)

    # --- "MORT OU VIF" tamponné, légèrement penché ---
    stamp_font = _load_font(_BOLD_CANDIDATES, 30)
    stamp_layer = _rotated_text("MORT OU VIF", stamp_font, INK_RED, angle=4)
    stamp_y = bounty_y + 75
    base.paste(
        stamp_layer,
        (int((WIDTH - stamp_layer.width) / 2), stamp_y),
        stamp_layer,
    )

    # --- Pied de page ---
    footer_font = _load_font(_REGULAR_CANDIDATES, 18)
    _draw_centered_text(base, "GOUVERNEMENT MONDIAL", HEIGHT - 45, footer_font, MUTED_BROWN)

    buffer = io.BytesIO()
    base.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def generate_wanted_poster(
    member: discord.Member,
    fleet_and_title: str,
    bounty: int,
) -> discord.File:
    """
    Version asynchrone : récupère l'avatar du membre depuis Discord, puis
    délègue la construction de l'image à generate_wanted_poster_sync().
    Retourne directement un discord.File prêt à être attaché à un message.
    """
    avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()

    buffer = generate_wanted_poster_sync(
        avatar_bytes=avatar_bytes,
        display_name=member.display_name,
        fleet_and_title=fleet_and_title,
        bounty=bounty,
    )

    return discord.File(buffer, filename="wanted_poster.png")
