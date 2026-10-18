"""Conservative, deterministic identities. Unknown sizes never auto-match."""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz.fuzz import token_sort_ratio

BRANDS = {"olpers": ["olper s", "olpers"], "nutella": ["nutella"],
          "surf excel": ["surf excel", "surfexcel"], "lays": ["lay s", "lays"],
          "national": ["national"], "shan": ["shan"], "tapal": ["tapal"],
          "lipton": ["lipton"], "dalda": ["dalda"], "nestle": ["nestle", "nestlé"],
          "peek freans": ["peek freans"], "mitchells": ["mitchell s", "mitchells"]}
SIZE_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(kilograms?|kgs?|grams?|gms?|gm|g|millilit(?:er|re)s?|ml|lit(?:er|re)s?|ltr?s?|l|pcs?|pieces?)\b")
VARIANT_WORDS = {"chocolate", "strawberry", "vanilla", "banana", "mango", "orange", "lemon", "lime",
                 "masala", "salted", "plain", "classic", "barbecue", "bbq", "chilli", "chili", "mint",
                 "skimmed", "skim", "lowfat", "lactosefree", "sugarfree", "diet", "light", "gold", "brown",
                 "white", "black", "green", "basmati", "sella", "refined", "wholewheat", "organic",
                 "automatic", "handwash", "topload", "frontload", "supreme", "danedar", "elaichi"}
PACKAGING = {"pouch", "bottle", "jar", "tin", "can", "sachet", "carton", "box"}
PACK_RE = re.compile(
    r"\b(?:pack\s*(?:of\s*)?|pk\s*)(\d+)\b"
    r"|\b(\d+)\s*(?:packs?|pk)\b"
    r"|\b(\d+)\s*[x×]\s*\d"
    r"|\b\d+(?:\.\d+)?\s*(?:ml|litres?|liters?|l|g|kg)\s*[x×]\s*(\d+)\b"
)


def normalize_text(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[’']", "", text)
    for pattern, replacement in [(r"\blow[ -]fat\b", "lowfat"), (r"\blactose[ -]free\b", "lactosefree"),
                                 (r"\bsugar[ -]free\b", "sugarfree"), (r"\bwhole[ -]wheat\b", "wholewheat"),
                                 (r"\btop[ -]load\b", "topload"), (r"\bfront[ -]load\b", "frontload"),
                                 (r"\bfull[ -]cream\b", "fullcream")]:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", text)).strip()


@dataclass(frozen=True)
class Identity:
    brand: str
    name: str
    quantity: Decimal | None
    unit: str
    pack_count: int
    variants: frozenset
    packaging: frozenset
    gtin: str = ""


def identify(title, brand="", gtin=""):
    text = normalize_text(re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", " x ", title, flags=re.IGNORECASE))
    canonical_brand = normalize_text(brand)
    for key, aliases in BRANDS.items():
        if canonical_brand in aliases or not canonical_brand and any(re.search(rf"\b{re.escape(a)}\b", text) for a in aliases):
            canonical_brand = key
            break
    quantity, unit = None, ""
    sizes = list(SIZE_RE.finditer(text))
    if len(sizes) == 1:
        size = sizes[0]
        quantity, raw_unit = Decimal(size[1]), size[2]
        if raw_unit.startswith(("kg", "kilogram")):
            quantity, unit = quantity * 1000, "g"
        elif raw_unit.startswith(("g",)):
            unit = "g"
        elif raw_unit.startswith(("ml", "millilit")):
            unit = "ml"
        elif raw_unit.startswith(("l",)):
            quantity, unit = quantity * 1000, "ml"
        else:
            unit = "pc"
        if quantity <= 0:
            quantity, unit = None, ""
    raw_lower = unicodedata.normalize("NFKC", title.lower())
    pack_counts = {int(next(v for v in match.groups() if v)) for match in PACK_RE.finditer(raw_lower)}
    pack_count = next(iter(pack_counts)) if len(pack_counts) == 1 else 1
    if len(pack_counts) > 1 or not 1 <= pack_count <= 32767:
        quantity, unit, pack_count = None, "", 1
    words = set(text.split())
    variants = words & VARIANT_WORDS
    variants = {"bbq" if w == "barbecue" else "chilli" if w == "chili" else "skimmed" if w == "skim" else w for w in variants}
    # Full cream/UHT/plain wording is a milk baseline; flavored/low-fat milk is guarded above.
    if "milk" in words:
        variants.discard("plain")
    name = SIZE_RE.sub(" ", text)
    name = re.sub(r"\b(?:pack\s*(?:of\s*)?|pk\s*)\d+\b|\b\d+\s*(?:packs?|pk)\b|\b\d+\s*x\b|\bx\s*\d+\b", " ", name)
    for alias in BRANDS.get(canonical_brand, [canonical_brand] if canonical_brand else []):
        name = re.sub(rf"\b{re.escape(alias)}\b", " ", name)
    removable = PACKAGING | {"uht", "fullcream", "litre", "liter"}
    name = " ".join(w for w in name.split() if w not in removable)
    return Identity(canonical_brand, name, quantity, unit, pack_count, frozenset(variants), frozenset(words & PACKAGING), gtin.strip())


def match_score(left, right):
    """Fuzzy matching only after hard compatibility checks. 92+ is eligible."""
    if left.quantity is None or right.quantity is None or not left.brand or not right.brand:
        return 0.0
    if (left.brand, left.quantity, left.unit, left.pack_count, left.variants) != (right.brand, right.quantity, right.unit, right.pack_count, right.variants):
        return 0.0
    if left.packaging != right.packaging:
        return 0.0
    if left.gtin and right.gtin:
        return 100.0 if left.gtin == right.gtin else 0.0
    return token_sort_ratio(left.name, right.name) if left.name and right.name else 0.0
