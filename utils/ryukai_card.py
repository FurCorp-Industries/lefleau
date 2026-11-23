"""Génération locale de la carte de profil RYUKAI."""

import io
import os

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 600
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_DIR = os.path.join(_BASE_DIR, "assets", "fonts")
_FONT_CANDIDATES = [
    os.path.join(_FONT_DIR, "ryukai.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]
_BOLD_FONT_CANDIDATES = [
    os.path.join(_FONT_DIR, "ryukai_bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
]


def _font(candidates: list[str], size: int):
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fitted_font(text: str, max_width: int, start_size: int, bold: bool = False):
    candidates = _BOLD_FONT_CANDIDATES if bold else _FONT_CANDIDATES
    for size in range(start_size, 13, -2):
        font = _font(candidates, size)
        if font.getlength(text) <= max_width:
            return font
    return _font(candidates, 13)


def _avatar(avatar_bytes: bytes, size: int) -> Image.Image:
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar.thumbnail((size, size), Image.LANCZOS)
    square = Image.new("RGBA", (size, size), (23, 19, 45, 255))
    square.paste(avatar, ((size - avatar.width) // 2, (size - avatar.height) // 2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((3, 3, size - 3, size - 3), fill=255)
    result = Image.new("RGBA", (size, size))
    result.paste(square, (0, 0), mask)
    return result


def _label(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, width: int):
    label_font = _font(_FONT_CANDIDATES, 20)
    value_font = _fitted_font(value.upper(), width, 30, bold=True)
    draw.text((x, y), label.upper(), font=label_font, fill=(173, 160, 197))
    draw.text((x, y + 27), value.upper(), font=value_font, fill=(246, 241, 255))


def _stat_box(draw: ImageDraw.ImageDraw, x: int, title: str, wins: int, losses: int):
    y, w, h = 407, 330, 132
    draw.rounded_rectangle((x, y, x + w, y + h), radius=7, fill=(20, 21, 45), outline=(57, 45, 89), width=2)
    draw.rectangle((x, y, x + w, y + 4), fill=(221, 68, 181))
    draw.text((x + 18, y + 20), title.upper(), font=_font(_FONT_CANDIDATES, 19), fill=(177, 165, 198))
    draw.text((x + 18, y + 51), str(wins), font=_font(_BOLD_FONT_CANDIDATES, 56), fill=(250, 246, 255))
    draw.text((x + 105, y + 72), f"W  ·  {losses} L", font=_font(_FONT_CANDIDATES, 18), fill=(177, 165, 198))


def generate_ryukai_card_sync(avatar_bytes: bytes, display_name: str, profile: dict) -> io.BytesIO:
    """Rend une carte PNG inspirée de la référence fournie, sans asset distant."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (15, 14, 31))
    draw = ImageDraw.Draw(image)

    # Surface principale et accent rose latéral.
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), radius=15, fill=(29, 25, 48), outline=(62, 48, 92), width=2)
    draw.rounded_rectangle((18, 18, 27, HEIGHT - 18), radius=5, fill=(235, 79, 185))
    draw.rounded_rectangle((51, 45, WIDTH - 52, 569), radius=12, fill=(31, 25, 57))

    # Motif diagonal discret, proche de la carte de référence.
    for offset in range(-300, WIDTH, 74):
        draw.line((offset, 390, offset + 300, 90), fill=(55, 44, 83), width=2)

    draw.rectangle((78, 76, 84, 132), fill=(236, 90, 191))
    draw.text((99, 70), "RYUKAI", font=_font(_BOLD_FONT_CANDIDATES, 50), fill=(250, 236, 255))
    draw.text((101, 124), "PLAYER CARD", font=_font(_FONT_CANDIDATES, 18), fill=(183, 167, 206))
    name_font = _fitted_font(display_name.upper(), 700, 44, bold=True)
    draw.text((79, 174), display_name.upper(), font=name_font, fill=(250, 246, 255))

    _label(draw, 79, 252, "Team", profile["team"], 190)
    _label(draw, 320, 252, "Rank", profile["rank_name"], 190)
    _label(draw, 561, 252, "Platform", profile["platform"], 235)
    _label(draw, 843, 252, "Region", profile["region"], 175)

    # Portrait avec double anneau magenta/orange.
    avatar_size = 154
    ax, ay = 976, 76
    draw.ellipse((ax - 11, ay - 11, ax + avatar_size + 11, ay + avatar_size + 11), fill=(237, 82, 184))
    draw.ellipse((ax - 6, ay - 6, ax + avatar_size + 6, ay + avatar_size + 6), fill=(250, 178, 69))
    portrait = _avatar(avatar_bytes, avatar_size)
    image.paste(portrait, (ax, ay), portrait)

    _stat_box(draw, 79, "War Wins", profile["war_wins"], profile["war_losses"])
    _stat_box(draw, 435, "Pub War Wins", profile["pub_war_wins"], profile["pub_war_losses"])
    _stat_box(draw, 791, "1v1 Wins", profile["duel_wins"], profile["duel_losses"])

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
