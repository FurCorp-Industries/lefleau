"""Génération locale de la carte de profil RYUKAI, thème dragon céleste."""

import io
import os

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 675
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_DIR = os.path.join(_BASE_DIR, "assets", "fonts")
_DRAGON_ASSET = os.path.join(_BASE_DIR, "assets", "ryukai", "celestial-dragon-crest.png")
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
    square = Image.new("RGBA", (size, size), (20, 21, 25, 255))
    square.paste(avatar, ((size - avatar.width) // 2, (size - avatar.height) // 2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((3, 3, size - 3, size - 3), fill=255)
    result = Image.new("RGBA", (size, size))
    result.paste(square, (0, 0), mask)
    return result


def _paste_dragon(image: Image.Image):
    """Pose l'emblème en filigrane, sans empêcher la lecture des données."""
    if not os.path.isfile(_DRAGON_ASSET):
        return
    dragon = Image.open(_DRAGON_ASSET).convert("RGBA")
    dragon.thumbnail((495, 495), Image.LANCZOS)
    alpha = dragon.getchannel("A").point(lambda value: value * 2 // 5)
    dragon.putalpha(alpha)
    image.paste(dragon, (684, 62), dragon)


def _label(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, width: int):
    label_font = _font(_FONT_CANDIDATES, 17)
    value_font = _fitted_font(value.upper(), width, 27, bold=True)
    draw.rectangle((x, y + 7, x + 4, y + 22), fill=(157, 35, 48))
    draw.text((x + 13, y), label.upper(), font=label_font, fill=(166, 172, 182))
    draw.text((x, y + 29), value.upper(), font=value_font, fill=(238, 239, 241))


def _stat_box(draw: ImageDraw.ImageDraw, x: int, title: str, wins: int, losses: int):
    y, w, h = 492, 314, 137
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=(18, 20, 26), outline=(75, 30, 37), width=2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 5), fill=(145, 31, 42))
    draw.text((x + 20, y + 20), title.upper(), font=_font(_FONT_CANDIDATES, 17), fill=(174, 180, 189))
    draw.text((x + 19, y + 48), str(wins), font=_font(_BOLD_FONT_CANDIDATES, 56), fill=(240, 241, 243))
    draw.text((x + 110, y + 74), "VICTOIRES", font=_font(_FONT_CANDIDATES, 15), fill=(151, 157, 168))
    draw.text((x + 20, y + 109), f"{losses} défaite{'s' if losses != 1 else ''}", font=_font(_FONT_CANDIDATES, 16), fill=(154, 49, 60))


def generate_ryukai_card_sync(avatar_bytes: bytes, display_name: str, profile: dict) -> io.BytesIO:
    """Rend la carte RYUKAI sous la forme d'un dossier de guerre draconique."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (9, 11, 15))
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        shade = 18 + int(y / HEIGHT * 12)
        draw.line((0, y, WIDTH, y), fill=(shade, shade + 2, shade + 6))
    draw.ellipse((782, 83, 1122, 423), fill=(70, 18, 25), outline=(135, 37, 48), width=2)
    for offset in range(-600, WIDTH, 72):
        draw.line((offset, HEIGHT, offset + 560, 0), fill=(31, 34, 41), width=1)

    _paste_dragon(image)
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), radius=16, outline=(116, 34, 45), width=2)
    draw.rounded_rectangle((29, 29, WIDTH - 29, HEIGHT - 29), radius=11, outline=(57, 62, 72), width=1)
    draw.rectangle((54, 56, 60, 132), fill=(157, 35, 48))
    draw.text((78, 52), "RYUKAI", font=_font(_BOLD_FONT_CANDIDATES, 47), fill=(239, 240, 242))
    draw.text((80, 109), "DRAGON DOSSIER  //  WAR ARCHIVE", font=_font(_FONT_CANDIDATES, 16), fill=(177, 181, 188))
    draw.line((78, 143, 590, 143), fill=(104, 33, 43), width=2)

    avatar_size, ax, ay = 150, 78, 183
    draw.ellipse((ax - 12, ay - 12, ax + avatar_size + 12, ay + avatar_size + 12), fill=(86, 22, 31), outline=(190, 193, 200), width=2)
    portrait = _avatar(avatar_bytes, avatar_size)
    image.paste(portrait, (ax, ay), portrait)

    name_font = _fitted_font(display_name.upper(), 420, 44, bold=True)
    draw.text((267, 186), display_name.upper(), font=name_font, fill=(247, 247, 248))
    draw.text((269, 244), "MEMBRE CERTIFIÉ RYUKAI", font=_font(_FONT_CANDIDATES, 16), fill=(174, 54, 66))
    _label(draw, 268, 292, "Team", profile["team"], 135)
    _label(draw, 445, 292, "Rank", profile["rank_name"], 140)
    _label(draw, 78, 383, "Platform", profile["platform"], 226)
    _label(draw, 370, 383, "Region", profile["region"], 170)

    draw.text((750, 439), "THE SILVER COIL", font=_font(_BOLD_FONT_CANDIDATES, 19), fill=(211, 214, 219))
    draw.text((752, 466), "RYUKAI WAR INTELLIGENCE", font=_font(_FONT_CANDIDATES, 14), fill=(165, 56, 67))

    _stat_box(draw, 78, "War Wins", profile["war_wins"], profile["war_losses"])
    _stat_box(draw, 443, "Pub War Wins", profile["pub_war_wins"], profile["pub_war_losses"])
    _stat_box(draw, 808, "1v1 Wins", profile["duel_wins"], profile["duel_losses"])

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
