"""Build Telegram-only Cairo Deals product cards from Amazon Egypt product pages."""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import io
import re
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
PRODUCT_PAGE = "https://www.amazon.eg/dp/{asin}"
IMAGE_HOSTS = {"m.media-amazon.com","images-na.ssl-images-amazon.com","images-eu.ssl-images-amazon.com",}
CARD_SIZE = (1080, 900)
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; CairoDealsBot/1.0; +https://t.me/cairo_deals)"
class _ImageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.image_url = None
    def handle_starttag(self, tag, attrs):
        values = {key.lower(): value for key, value in attrs if key}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image", "twitter:image"}: self.image_url = values.get("content") or self.image_url
        elif tag.lower() == "img" and values.get("data-old-hires"): self.image_url = values["data-old-hires"]
def _valid_image_url(url: str | None) -> bool:
    try:
        parsed = urlparse(url or "")
        return parsed.scheme == "https" and (parsed.hostname or "").lower() in IMAGE_HOSTS and parsed.port in (None, 443) and not parsed.username and not parsed.password
    except ValueError: return False
def find_amazon_product_image(asin: str, *, session=None) -> str:
    if not re.fullmatch(r"[A-Z0-9]{10}", (asin or "").upper()): raise ValueError("Invalid Amazon ASIN")
    client = session or requests.Session(); owns_session = session is None
    try:
        response = client.get(PRODUCT_PAGE.format(asin=asin.upper()), headers={"User-Agent": USER_AGENT, "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.7"}, timeout=(8, 18))
        response.raise_for_status(); parser = _ImageParser(); parser.feed(response.text)
        if not _valid_image_url(parser.image_url): raise ValueError("Amazon page did not expose an approved Amazon CDN image")
        return parser.image_url
    finally:
        if owns_session: client.close()
def _load_product_image(url: str, *, session=None) -> Image.Image:
    if not _valid_image_url(url): raise ValueError("Product image URL is not on an approved Amazon image CDN")
    client = session or requests.Session(); owns_session = session is None
    try:
        response = client.get(url, timeout=(8, 20), stream=True, headers={"User-Agent": USER_AGENT}); response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"): raise ValueError("Amazon image response is not an image")
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES: raise ValueError("Product image exceeds the size limit")
        image = Image.open(io.BytesIO(data)); image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    finally:
        if owns_session: client.close()
def _shape(text: str) -> str:
    # FIX: Pillow with libraqm already does Arabic shaping + bidi.
    # Old code did arabic_reshaper + get_display AND Pillow did it again -> double-shaped = mirrored text.
    # Return text as-is and let Pillow shape it via direction='rtl', language='ar' in draw.text.
    return str(text)
def _font(size: int, bold: bool = False):
    # Prefer an Arabic-capable font first so Arabic doesn't render as boxes.
    candidates = (
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for path in candidates:
        if Path(path).is_file(): return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()
def _fit_font(draw, text: str, max_width: int, start: int, min_size: int = 30):
    for size in range(start, min_size - 1, -2):
        font = _font(size, bold=True)
        if draw.textbbox((0, 0), text, font=font, direction="rtl", language="ar")[2] <= max_width: return font
    return _font(min_size, bold=True)
def create_telegram_product_card(*, asin: str, product_name: str, price: str, output_path: str | Path, image_url: str | None = None, session=None) -> Path:
    name = re.sub(r"\s+", " ", (product_name or "")).strip(); amount = re.sub(r"\s+", " ", (price or "")).strip()
    if not name or len(name) > 120 or not amount or len(amount) > 40: raise ValueError("Product name or advertised price is invalid")
    product_url = image_url or find_amazon_product_image(asin, session=session)
    product = _load_product_image(product_url, session=session)
    canvas = Image.new("RGB", CARD_SIZE, "white"); draw = ImageDraw.Draw(canvas)
    # Layout for 1080x900: image on RIGHT, text on LEFT
    image_area = (580, 60, 1008, 700)
    fitted = ImageOps.contain(product, (image_area[2] - image_area[0], image_area[3] - image_area[1]))
    x = image_area[0] + (image_area[2] - image_area[0] - fitted.width) // 2
    y = image_area[1] + (image_area[3] - image_area[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    # Text on LEFT: name on 2 lines so font stays big and readable, price below it
    words = name.split(" ")
    # Split into 2 balanced lines (RTL: first half is right side, Pillow handles it)
    mid = (len(words) + 1) // 2
    line1 = " ".join(words[:mid]); line2 = " ".join(words[mid:])
    name_font = _fit_font(draw, _shape(line1 if len(line1) >= len(line2) else line2), 440, 58, 36)
    # FIX: RTL text must be anchored on the RIGHT (x=512), not left.
    # Left anchor with RTL clips the first digits (625 -> 6, 485 -> 385).
    draw.text((512, 200), _shape(line1), fill="#202124", font=name_font, direction="rtl", language="ar", anchor="ra")
    if line2:
        draw.text((512, 285), _shape(line2), fill="#202124", font=name_font, direction="rtl", language="ar", anchor="ra")
    shaped_price = _shape(f"{amount}"); price_font = _fit_font(draw, shaped_price, 440, 72, 44)
    draw.text((512, 450), shaped_price, fill="#D62828", font=price_font, direction="rtl", language="ar", anchor="ra")
    # Footer: black bar at bottom, follow text INSIDE it (y 790-900, text at 825)
    draw.rectangle((0, 790, 1080, 900), fill="#202124")
    follow = _shape("تابعنا على تليجرام  •  تابعنا على فيسبوك")
    follow_font = _fit_font(draw, follow, 900, 32, 24)
    follow_box = draw.textbbox((0, 0), follow, font=follow_font, direction="rtl", language="ar")
    draw.text(((1080 - (follow_box[2] - follow_box[0])) // 2, 825), follow, fill="white", font=follow_font, direction="rtl", language="ar")
    destination = Path(output_path); destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="JPEG", quality=92, optimize=True)
    return destination
