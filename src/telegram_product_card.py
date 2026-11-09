"""Build Telegram-only Cairo Deals product cards from Amazon Egypt product pages."""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
import json
from urllib.parse import urlparse
import io
import re
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
PRODUCT_PAGE = "https://www.amazon.eg/dp/{asin}"
IMAGE_HOSTS = {"m.media-amazon.com","images-na.ssl-images-amazon.com","images-eu.ssl-images-amazon.com",}
CARD_SIZE = (1080, 1350)

BLUE = "#0757B8"
DARK_BLUE = "#12345A"
YELLOW = "#FFC928"
RED = "#E53935"
INK = "#172B45"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; CairoDealsBot/1.0; +https://t.me/cairo_deals)"
class _ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url = None
        self.title = None
        self.price = None
        self._inside_product_title = False
        self._title_parts = []
        self._inside_price = False
        self._price_depth = 0
        self._price_parts = []

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): value for key, value in attrs if key}
        classes = set((values.get("class") or "").split())
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image", "twitter:image"}:
                self.image_url = values.get("content") or self.image_url
            elif key in {"og:title", "twitter:title"}:
                self.title = values.get("content") or self.title
            elif key in {"product:price:amount", "og:price:amount", "price"}:
                self.price = values.get("content") or self.price
        elif tag.lower() == "span" and values.get("id") == "productTitle":
            self._inside_product_title = True
        elif tag.lower() in {"div", "span"} and "a-price" in classes:
            self._inside_price = True
            self._price_depth += 1
        elif tag.lower() == "span" and "a-offscreen" in classes and self._inside_price:
            self._price_depth += 1
        elif tag.lower() == "img":
            if values.get("data-old-hires"):
                self.image_url = values["data-old-hires"]
            elif values.get("data-a-dynamic-image"):
                try:
                    choices = json.loads(values["data-a-dynamic-image"])
                    self.image_url = next(iter(choices), self.image_url)
                except (TypeError, ValueError):
                    pass
            elif values.get("src") and _valid_image_url(values["src"]):
                self.image_url = values["src"]

    def handle_data(self, data):
        if self._inside_product_title:
            self._title_parts.append(data)
        if self._inside_price and data.strip():
            self._price_parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() == "span" and self._inside_product_title:
            self._inside_product_title = False
            parsed = " ".join(" ".join(self._title_parts).split())
            if parsed:
                self.title = parsed
        if tag.lower() in {"div", "span"} and self._inside_price:
            self._price_depth -= 1
            if self._price_depth <= 0:
                self._inside_price = False
                parsed_price = " ".join(" ".join(self._price_parts).split())
                if parsed_price and not self.price:
                    self.price = parsed_price

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
def find_amazon_product_details(asin: str, *, session=None) -> dict:
    """Fetch Amazon page once, return live image + title + price. No API needed."""
    if not re.fullmatch(r"[A-Z0-9]{10}", (asin or "").upper()): raise ValueError("Invalid Amazon ASIN")
    client = session or requests.Session(); owns_session = session is None
    try:
        response = client.get(PRODUCT_PAGE.format(asin=asin.upper()), headers={"User-Agent": USER_AGENT, "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.7"}, timeout=(8, 18))
        response.raise_for_status(); parser = _ImageParser(); parser.feed(response.text)
        out = {}
        if _valid_image_url(parser.image_url): out["image_url"] = parser.image_url
        if parser.title: out["title"] = parser.title.strip()
        if parser.price:
            raw_price = parser.price.strip()
            normalized = raw_price.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
            normalized = normalized.replace("٫", ".").replace("٬", "").replace(",", "")
            match = re.search(r"\\d+(?:\\.\\d{1,2})?", normalized)
            if match:
                amount = float(match.group(0))
                out["price"] = f"{amount:.2f} جنيه".replace(".00 جنيه", " جنيه")
        return out
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



def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    try:
        return draw.textlength(text, font=font, direction="rtl", language="ar")
    except (TypeError, ValueError):
        return draw.textlength(text, font=font)


def _draw_rtl(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, anchor="mm"):
    try:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl", language="ar")
    except (TypeError, ValueError):
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _wrap_name(draw: ImageDraw.ImageDraw, name: str, font, max_width: int) -> list[str]:
    words = name.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2] or [name[:50]]
def create_telegram_product_card(
    *,
    asin: str,
    product_name: str,
    price: str,
    output_path: str | Path,
    image_url: str | None = None,
    session=None,
) -> Path:
    """Create a branded card using the existing product image, name, and price."""
    name = re.sub(r"\s+", " ", (product_name or "")).strip()
    amount = re.sub(r"\s+", " ", (price or "")).strip()
    if not name or len(name) > 120 or not amount or len(amount) > 40:
        raise ValueError("Product name or advertised price is invalid")

    # Keep the current image source; fit the complete image without cropping.
    product_url = image_url or find_amazon_product_image(asin, session=session)
    product = _load_product_image(product_url, session=session)

    canvas = Image.new("RGB", CARD_SIZE, "#F7FAFF")
    draw = ImageDraw.Draw(canvas)

    # Brand header.
    draw.rounded_rectangle((42, 34, 1038, 166), radius=34, fill="white", outline="#DCE9F8", width=3)
    draw.ellipse((70, 60, 150, 140), fill=BLUE)
    draw.line((91, 84, 101, 84, 111, 112, 135, 112), fill="white", width=6)
    draw.line((105, 96, 132, 96), fill="white", width=5)
    draw.ellipse((111, 119, 120, 128), fill=YELLOW)
    draw.ellipse((130, 119, 139, 128), fill=YELLOW)
    draw.text((178, 67), "Cairo", font=_font(42, True), fill=BLUE)
    draw.text((178, 111), "Deals", font=_font(34, True), fill=RED)
    draw.rounded_rectangle((690, 69, 990, 130), radius=28, fill=YELLOW)
    _draw_rtl(draw, (840, 100), "عرض جديد", _font(34, True), DARK_BLUE)

    # Full product image, contained inside a clean white frame.
    draw.rounded_rectangle((42, 194, 1038, 876), radius=38, fill="white", outline="#DCE9F8", width=3)
    image_area = (88, 226, 992, 844)
    fitted = ImageOps.contain(
        product,
        (image_area[2] - image_area[0], image_area[3] - image_area[1]),
        method=Image.Resampling.LANCZOS,
    )
    image_x = image_area[0] + (image_area[2] - image_area[0] - fitted.width) // 2
    image_y = image_area[1] + (image_area[3] - image_area[1] - fitted.height) // 2
    canvas.paste(fitted, (image_x, image_y))

    # Product name from the existing source flow.
    title_font = _font(47, True)
    title_lines = _wrap_name(draw, name, title_font, 930)
    title_y = 930
    for line in title_lines:
        fitted_font = _fit_font(draw, line, 930, 47, 30)
        _draw_rtl(draw, (540, title_y), line, fitted_font, INK)
        title_y += 62

    # Show only the supplied price; never invent a previous price or discount.
    draw.rounded_rectangle((180, 1072, 900, 1200), radius=34, fill=RED)
    _draw_rtl(draw, (540, 1136), amount, _fit_font(draw, amount, 650, 68, 38), "white")

    draw.rounded_rectangle((42, 1230, 1038, 1320), radius=30, fill=BLUE)
    footer = "رابط الشراء المباشر في نص الإعلان"
    _draw_rtl(draw, (540, 1275), footer, _fit_font(draw, footer, 900, 35, 25), "white")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="JPEG", quality=93, optimize=True)
    return destination
