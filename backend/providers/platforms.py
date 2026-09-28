"""
Where a listing lives, and what a good listing looks like there.

This module replaces the single most dangerous line in the old provider:

    domain = _DOMAINS.get(platform.lower(), "amazon.com")

A platform the system did not recognise was silently searched on Amazon, so a
Shopify seller received ten Amazon competitors labelled as their own platform's
top sellers. Confidently wrong, with nothing in the output to reveal it. Here an
unrecognised domain resolves to `dtc` — somebody's own store, which is what an
unfamiliar domain almost always is — and never to a marketplace.

The second job is the `PlatformProfile`. A 200-character keyword-stacked title
with five bullets is excellent on a marketplace and terrible on a brand's own
product page; the reverse is equally true. Scoring competitors from several
platforms against one set of format assumptions produces a benchmark that
measures house style rather than listing quality. The profile is what lets the
rubric and the rewrite generator speak in platform-relative terms.

Pure data and pure functions: no I/O, no model calls, importable from both
`providers/` and `agents/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from normalize import registrable_domain

# The slug used when a domain is not a marketplace we know. It is a real
# answer, not a failure: an unrecognised ecommerce domain is a direct-to-
# consumer store.
DTC = "dtc"


@dataclass(frozen=True)
class PlatformProfile:
    """How listings are shaped on one platform."""

    slug: str
    label: str
    domains: tuple[str, ...] = ()
    is_marketplace: bool = True
    # Can we scope a web search to this platform with `site:`? False for DTC,
    # which has no single domain.
    searchable: bool = True
    # The observed norm for title length, used as guidance, never as a rule.
    title_char_target: tuple[int, int] = (60, 200)
    bullets_expected: bool = True
    typical_bullets: int = 5
    # False where the description field is images rather than text, so an empty
    # description means "not extractable", not "the seller wrote nothing".
    description_is_text: bool = True
    note: str = ""


_PROFILES: dict[str, PlatformProfile] = {
    "amazon": PlatformProfile(
        slug="amazon", label="Amazon",
        domains=("amazon.com", "amazon.co.uk", "amazon.de", "amazon.ca",
                 "amazon.com.au", "amazon.fr", "amazon.it", "amazon.es",
                 "amazon.co.jp", "amazon.in", "amazon.com.mx", "amazon.nl",
                 "amazon.se", "amazon.ae", "amazon.sa", "amazon.sg"),
        title_char_target=(150, 200), bullets_expected=True, typical_bullets=5,
        description_is_text=False,
        note="A+ content is images, so an empty description is common and is not a gap.",
    ),
    "walmart": PlatformProfile(
        slug="walmart", label="Walmart", domains=("walmart.com", "walmart.ca"),
        title_char_target=(75, 150), typical_bullets=4,
    ),
    "ebay": PlatformProfile(
        slug="ebay", label="eBay",
        domains=("ebay.com", "ebay.co.uk", "ebay.de", "ebay.com.au", "ebay.ca"),
        title_char_target=(60, 80), bullets_expected=False, typical_bullets=0,
        note="80-character title cap; copy lives in a free-form HTML description.",
    ),
    "etsy": PlatformProfile(
        slug="etsy", label="Etsy", domains=("etsy.com",),
        title_char_target=(60, 140), bullets_expected=False, typical_bullets=0,
    ),
    "target": PlatformProfile(
        slug="target", label="Target", domains=("target.com",),
        title_char_target=(60, 120), typical_bullets=4,
    ),
    "bestbuy": PlatformProfile(
        slug="bestbuy", label="Best Buy", domains=("bestbuy.com", "bestbuy.ca"),
        title_char_target=(60, 120), typical_bullets=4,
    ),
    "iherb": PlatformProfile(
        slug="iherb", label="iHerb", domains=("iherb.com",),
        title_char_target=(50, 120), typical_bullets=4,
    ),
    "aliexpress": PlatformProfile(
        slug="aliexpress", label="AliExpress", domains=("aliexpress.com", "aliexpress.us"),
        title_char_target=(60, 128), bullets_expected=False, typical_bullets=0,
    ),
    "daraz": PlatformProfile(
        slug="daraz", label="Daraz",
        domains=("daraz.lk", "daraz.pk", "daraz.com.bd", "daraz.com.np"),
        title_char_target=(60, 120), typical_bullets=4,
    ),
    "noon": PlatformProfile(
        slug="noon", label="Noon", domains=("noon.com",),
        title_char_target=(60, 120), typical_bullets=4,
    ),
    "shopify": PlatformProfile(
        slug="shopify", label="Shopify store", domains=("myshopify.com",),
        is_marketplace=False, searchable=False,
        title_char_target=(20, 70), bullets_expected=False, typical_bullets=0,
        note="Brand-led short titles; the selling copy is prose, not bullets.",
    ),
    DTC: PlatformProfile(
        slug=DTC, label="Brand site", domains=(),
        is_marketplace=False, searchable=False,
        title_char_target=(20, 70), bullets_expected=False, typical_bullets=0,
        note="A brand's own store. Short product names, long-form prose.",
    ),
    "generic": PlatformProfile(
        slug="generic", label="Other", domains=(),
        is_marketplace=False, searchable=False,
        title_char_target=(40, 140), bullets_expected=False, typical_bullets=0,
    ),
}

# Regional aliases. The user's platform selector and the Rainforest provider both
# speak these; they fold to a canonical slug but keep their own search domain.
_ALIASES: dict[str, tuple[str, str]] = {
    "amazon":     ("amazon", "amazon.com"),
    "amazon_us":  ("amazon", "amazon.com"),
    "amazon_uk":  ("amazon", "amazon.co.uk"),
    "amazon_de":  ("amazon", "amazon.de"),
    "amazon_ca":  ("amazon", "amazon.ca"),
    "amazon_au":  ("amazon", "amazon.com.au"),
    "amazon_in":  ("amazon", "amazon.in"),
    "amazon_ae":  ("amazon", "amazon.ae"),
}

# Longest domain first so "amazon.com.au" wins over "amazon.com".
_DOMAIN_INDEX: list[tuple[str, str]] = sorted(
    ((d, p.slug) for p in _PROFILES.values() for d in p.domains),
    key=lambda pair: len(pair[0]), reverse=True,
)


def canonical(platform: str) -> str:
    """Fold a regional alias to its canonical slug. Unknown input -> 'generic'."""
    key = (platform or "").strip().lower()
    if key in _ALIASES:
        return _ALIASES[key][0]
    return key if key in _PROFILES else "generic"


def detect(url: str) -> str:
    """
    The platform slug for a product URL.

    An unrecognised domain returns `dtc`, never a marketplace. That is the whole
    point of this function.
    """
    host = registrable_domain(url)
    if not host:
        return "generic"
    for domain, slug in _DOMAIN_INDEX:
        if host == domain or host.endswith("." + domain):
            return slug
    return DTC


def profile(platform: str) -> PlatformProfile:
    """The format profile for a platform slug or alias."""
    return _PROFILES[canonical(platform)]


def domain_for(platform: str) -> str:
    """
    The domain to scope a search to, or "" when the platform has no single one.

    Returns "" for DTC, Shopify and generic — there is no `site:` to write, and
    a caller must not invent one.
    """
    key = (platform or "").strip().lower()
    if key in _ALIASES:
        return _ALIASES[key][1]
    prof = _PROFILES.get(canonical(key))
    return prof.domains[0] if prof and prof.searchable and prof.domains else ""


# Merchant names as Google Shopping reports them in `source`. Shopping results
# carry no merchant URL — only a google.com redirect — so the merchant name is
# the only platform signal they have.
_MERCHANT_HINTS: tuple[tuple[str, str], ...] = (
    ("amazon", "amazon"),
    ("walmart", "walmart"),
    ("ebay", "ebay"),
    ("etsy", "etsy"),
    ("target", "target"),
    ("best buy", "bestbuy"),
    ("bestbuy", "bestbuy"),
    ("iherb", "iherb"),
    ("aliexpress", "aliexpress"),
    ("daraz", "daraz"),
    ("noon", "noon"),
)


def from_merchant(merchant: str) -> str:
    """
    Platform slug for a merchant name, when no usable URL is available.

    Anything unrecognised is a brand selling direct — which is what a merchant
    name that is not a marketplace almost always means ("Life Extension",
    "Thorne", "Nature Made").
    """
    name = (merchant or "").strip().lower()
    if not name:
        return "generic"
    for needle, slug in _MERCHANT_HINTS:
        if needle in name:
            return slug
    return DTC


def label_for(platform: str) -> str:
    return profile(platform).label


def all_slugs() -> list[str]:
    return sorted(_PROFILES)
