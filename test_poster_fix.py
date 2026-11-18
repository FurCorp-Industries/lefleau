import io
from PIL import Image, ImageDraw
from utils.image_gen import generate_wanted_poster_sync

avatar = Image.new("RGB", (256, 256), (255, 140, 0))
d = ImageDraw.Draw(avatar)
d.ellipse([60, 40, 196, 176], fill=(255, 255, 255))
d.ellipse([85, 80, 115, 110], fill=(0, 0, 0))
d.ellipse([141, 80, 171, 110], fill=(0, 0, 0))
d.arc([90, 110, 166, 160], start=0, end=180, fill=(0, 0, 0), width=6)
buf = io.BytesIO()
avatar.save(buf, format="PNG")
avatar_bytes = buf.getvalue()

result = generate_wanted_poster_sync(
    avatar_bytes=avatar_bytes,
    display_name="Maxana",
    fleet_and_title="Fléaux de la Galaxie | Moussaillon Inconnu",
    bounty=0,
)
with open("test_poster_fix.png", "wb") as f:
    f.write(result.getvalue())
print("✅ généré")
