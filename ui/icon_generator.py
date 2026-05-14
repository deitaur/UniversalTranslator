"""
Icon generation for the application
"""

from PIL import Image, ImageDraw, ImageFont
from config import CONFIG_DIR, ICON_FILE

def _font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()

def generate_app_icon():
    """Create a beautiful .ico file for the desktop shortcut."""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    for sz in sizes:
        img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        m = max(1, sz // 32)  # margin scale

        # Gradient-like background circle
        d.ellipse([m, m, sz - m, sz - m], fill=(30, 30, 46, 240))
        d.ellipse([m + 1, m + 1, sz - m - 1, sz - m - 1], outline=(137, 180, 250, 120), width=max(1, sz // 32))

        # "T" letter centered
        try:
            font = ImageFont.truetype("arial.ttf", int(sz * 0.55))
        except OSError:
            font = ImageFont.load_default()
        bbox = d.textbbox((0, 0), "T", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (sz - tw) // 2 - bbox[0]
        ty = (sz - th) // 2 - bbox[1] - int(sz * 0.03)
        d.text((tx, ty), "T", fill=(137, 180, 250), font=font)

        # Small arrow at bottom-right
        arrow_sz = max(sz // 5, 4)
        ax = sz - arrow_sz - m * 2
        ay = sz - arrow_sz - m * 2
        d.polygon([
            (ax, ay),
            (ax + arrow_sz, ay + arrow_sz // 2),
            (ax, ay + arrow_sz),
        ], fill=(166, 227, 161))

        images.append(img)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    images[0].save(str(ICON_FILE), format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    return str(ICON_FILE)