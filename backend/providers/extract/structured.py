"""
schema.org Product data, parsed in Python.

Most ecommerce platforms emit a `<script type="application/ld+json">` block
describing the product: name, brand, description, price, aggregate rating. It is
published deliberately, for search engines, and it is exact.

Reading it first means the common case costs nothing and cannot hallucinate. The
model pass exists only for what this does not find — which keeps extraction
inside the project's rule that the model supplies judgement and Python supplies
facts.

Uses the stdlib HTML parser rather than a DOM library: we need the contents of
one tag type, and a real-world product page is frequently malformed enough that
a strict parser is a liability.
"""
from __future__ import annotations

import json
import logging
import re
from html import unescape
from html.parser import HTMLParser

log = logging.getLogger("listingiq.providers.structured")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


class _LdJsonCollector(HTMLParser):
    """Collects the body of every ld+json script tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._capturing = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        attr = {k.lower(): (v or "").lower() for k, v in attrs}
        if "ld+json" in attr.get("type", ""):
            self._capturing = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._capturing:
            self.blocks.append("".join(self._buf))
            self._capturing = False
            self._buf = []

    def handle_data(self, data):
        if self._capturing:
            self._buf.append(data)

    # A malformed page must not abort extraction.
    def error(self, message):  # pragma: no cover - stdlib compatibility
        pass


def _walk(node):
    """Yield every dict in a nested JSON-LD structure, graphs included."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _is_product(node: dict) -> bool:
    t = node.get("@type")
    types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
    return any(str(x).lower() in ("product", "productgroup", "individualproduct")
               for x in types)


def _text(value) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        for key in ("name", "value", "@value", "text"):
            if key in value:
                return _text(value[key])
    if isinstance(value, list) and value:
        return _text(value[0])
    return ""


def _number(value) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _int(value) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def clean_text(raw: str) -> str:
    """Strip markup and normalise whitespace, keeping paragraph breaks."""
    if not raw:
        return ""
    text = unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _offer_price(node: dict) -> str:
    """The listed price, as a display string, from an Offer or AggregateOffer."""
    offers = node.get("offers")
    for offer in _walk(offers):
        price = offer.get("price") or offer.get("lowPrice")
        if price in (None, ""):
            continue
        currency = str(offer.get("priceCurrency") or "").upper()
        symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, "")
        value = str(price).strip()
        if symbol:
            return f"{symbol}{value}"
        return f"{value} {currency}".strip()
    return ""


def parse_product(html: str) -> dict:
    """
    Extract a product from a page's JSON-LD. Returns {} when there is none.

    Never guesses: a field that is not present in the markup is simply absent
    from the result, so the model pass can be asked for exactly those and no
    more.
    """
    if not html:
        return {}

    collector = _LdJsonCollector()
    try:
        collector.feed(html)
    except Exception as e:            # a malformed page is normal, not an error
        log.debug("ld+json scan failed: %s", e)

    best: dict = {}
    for block in collector.blocks:
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for node in _walk(data):
            if not isinstance(node, dict) or not _is_product(node):
                continue
            found = {
                "title": _text(node.get("name")),
                "description": _text(node.get("description")),
                "brand_name": _text(node.get("brand")),
                "price": _offer_price(node),
            }
            rating = node.get("aggregateRating") or {}
            if isinstance(rating, dict):
                found["rating"] = _number(rating.get("ratingValue"))
                found["review_count"] = _int(
                    rating.get("reviewCount") or rating.get("ratingCount"))
            # Prefer the richest Product node on the page; pages often carry a
            # thin breadcrumb Product alongside the real one.
            if len(found.get("description") or "") > len(best.get("description") or ""):
                best = {k: v for k, v in found.items() if v not in ("", 0, 0.0)}
            elif not best:
                best = {k: v for k, v in found.items() if v not in ("", 0, 0.0)}

    return best


_BULLET_RE = re.compile(r"^\s{0,3}(?:[-*+\u2022\u25cf\u25aa]|\d{1,2}[.)])\s+(.{3,300})$")
# Any markdown link, and any bracketed fragment — a breadcrumb trail, a footer
# column or a truncated nav item arrives as `[**Amazon Music** Stream millions\`,
# which has no closing paren and so escaped a stricter pattern.
_MD_LINK_RE = re.compile(r"\]\(|^\s*\[|!\[|\\$")

# Interface furniture that a storefront renders as list items. Observed live on
# real product pages: "open prime modalclose prime modal", category breadcrumbs
# and account menus all arrive as perfectly well-formed markdown bullets.
_CHROME_MARKERS = (
    "prime modal", "add to cart", "add to list", "buy now", "sign in", "your account",
    "customer service", "gift cards", "registry", "best sellers", "today's deals",
    "return policy", "shipping policy", "privacy policy", "terms of service",
    "cookie", "newsletter", "subscribe", "follow us", "skip to", "see more",
    "view cart", "wish list", "select the department", "all departments",
    "size chart", "share this", "back to top",
    # Error and player furniture, observed on live pages. "Try disabling your
    # extensions." was being kept as a competitor's only selling point, and the
    # listing was then scored on it.
    "try disabling", "javascript is disabled", "enable javascript",
    "browser is not supported", "something went wrong", "please try again",
    "the video showcases", "the video guides", "click to play", "video player",
    "loading", "sorry, we", "we're sorry",
)

# Variant pickers render as list items: "90 Count (Pack of 1)", "Size: Large".
_VARIANT_RE = re.compile(
    r"^\s*(?:\d+\s*(?:count|ct|pack|pcs|capsules|tablets|servings|oz|ml|g|mg)\b"
    r"|(?:size|color|colour|flavor|flavour|style|scent)\s*[:=])",
    re.I)

# Subscription and delivery pickers. Observed live: a competitor's only "selling
# points" were "Delivery every 30 Days" and "Delivery every 45 Days", which were
# scored on the rubric and then reported to the customer as that brand's
# competitive strategy.
_SUBSCRIPTION_RE = re.compile(
    r"\b(?:every|per)\s+\d+\s*(?:day|week|month)s?\b"
    r"|\b(?:one[- ]time purchase|auto[- ]?deliver|ships? every|deliver every"
    r"|subscribe (?:&|and) save|recurring delivery)\b",
    re.I)

# Buying-guide prose. A page that tells the reader how to choose between brands
# is not a seller describing its own product — "Look for brands that use
# high-quality, pure magnesium glycinate" was captured from a retailer's advice
# section and scored as though that retailer had written it about itself.
_GUIDE_RE = re.compile(
    r"\b(?:look for|make sure (?:you|to)|be sure to|when (?:choosing|buying|shopping)"
    r"|check (?:for|that)|avoid (?:blends|products|brands)|some brands"
    r"|we recommend|our (?:top )?pick|consider (?:a|an|the|whether))\b",
    re.I)


def _is_chrome(text: str) -> bool:
    """
    Whether a list item is page furniture rather than a selling point.

    This matters more than it looks. Navigation captured as bullet points does
    two kinds of damage: it is scored on the rubric as though the seller wrote
    it, and it makes the listing look like it already *has* bullet points, so
    the model is never asked to find the real ones.
    """
    low = text.casefold()
    if _MD_LINK_RE.search(text):
        return True
    # Breadcrumbs arrive as their own list items.
    if text.strip() in ("\u203a", ">", "/", "|", "-"):
        return True
    if any(marker in low for marker in _CHROME_MARKERS):
        return True
    # Real copy is mostly letters and spaces. Menus are punctuation, symbols and
    # run-together words.
    letters = sum(1 for ch in text if ch.isalpha() or ch.isspace())
    if letters / max(1, len(text)) < 0.75:
        return True
    # A variant picker is a bare label ("90 Count (Pack of 1)"). A selling point
    # that happens to open with a quantity carries on into a sentence — "200
    # servings per container, NSF Certified for Sport" is copy, not a dropdown.
    if len(text) <= 40 and _VARIANT_RE.match(text):
        return True
    if _SUBSCRIPTION_RE.search(text):
        return True
    if _GUIDE_RE.search(text):
        return True
    # A selling point is a phrase, not one word.
    return len(text.split()) < 4


def bullets_from_markdown(markdown: str, limit: int = 8) -> list[str]:
    """
    Bullet points as the page actually renders them.

    Sellers put selling points in a real list; taking them verbatim keeps them
    out of the model's hands, where they would be paraphrased. But so does every
    navigation menu on the page, so each candidate has to earn its place.
    """
    out: list[str] = []
    for line in (markdown or "").splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        text = clean_text(m.group(1))
        if len(text) < 20 or text.lower().startswith(("http", "www.")):
            continue
        if _is_chrome(text):
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


# Storefronts prefix the page title with their own name, which then pollutes
# title-length statistics and the brand heuristics.
_TITLE_PREFIX_RE = re.compile(
    r"^\s*(amazon(?:\.[a-z.]+)?|walmart(?:\.com)?|ebay|etsy|target|best buy)\s*[:\-\u2013|]\s*",
    re.I)
_TITLE_SUFFIX_RE = re.compile(
    r"\s+[|\u2013-]\s+(?:Amazon\.com|Walmart\.com|eBay|Etsy|Target)\b.*$", re.I)


def strip_marketplace_prefix(title: str) -> str:
    """'Amazon.com: Pure Encapsulations Magnesium' -> 'Pure Encapsulations Magnesium'."""
    cleaned = _TITLE_PREFIX_RE.sub("", title or "").strip()
    cleaned = _TITLE_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned or (title or "").strip()
