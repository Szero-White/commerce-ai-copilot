"""Query analysis: turns a question into search terms using the corpus itself.

Nothing here knows a product name or a sample question. Two kinds of knowledge are used:
* a small closed list of Vietnamese/English function words (`STOP`) with the accented readings they have as function
  words (`FUNCTION_FORMS`), and
* the vocabulary of the indexed documents (`Lexicon`), which decides whether a spelling that can be a function word
  ("ban" = bạn / bán / bàn) is also a real content word of this catalogue.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from .quantities import extract, parse_conditions

MAX_TERMS = 10
# Typo repair is only attempted when few words need it, otherwise the query is probably not about this catalogue.
MAX_CORRECTIONS = 2


def normalize(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def raw_tokens(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())


STOP = set("""toi minh ban cho ve va la co khong nao gi bao nhieu the nao thu duoc cua voi trong mot khi hay can
giup xem tim san pham loai hang lau may nhu nay hom muon xin mua tren cac nhung moi da dang se rat qua
hoac neu thi de di ra vao what is the a an of in do you can i how much are there for to who tell me
it be on at by with and or my your we this that does did will would should could any some about
dau ap dung phai come get have has was were if because when while from just
vay nhe nhi oi ha nha hen shop ben theo mon cai chiec no kia sao""".split())

# Function words that are ALSO spellings of content words once diacritics are dropped. The value lists the readings
# (as typed, with diacritics) in which the word really is a function word. A word typed with diacritics that is not
# listed ("bàn", "da", "máy", "đầu") is therefore content; a word typed without diacritics is ambiguous and is only
# kept when the indexed documents actually use another reading of that spelling (see Lexicon.has_other_reading).
FUNCTION_FORMS = {
    "ban": {"bạn", "bán"}, "may": {"mấy", "may"}, "da": {"đã"}, "dau": {"đâu"}, "lau": {"lâu"}, "de": {"để"},
    "can": {"cần", "can"}, "dang": {"đang"}, "thu": {"thử", "thứ"}, "moi": {"mỗi", "mọi"}, "ve": {"về"},
    "co": {"có"}, "khong": {"không"}, "nao": {"nào"}, "gi": {"gì"}, "nhieu": {"nhiêu"}, "the": {"thế", "the"},
    "duoc": {"được"}, "cua": {"của"}, "voi": {"với"}, "mot": {"một"}, "toi": {"tôi"}, "minh": {"mình"},
    "giup": {"giúp"}, "tim": {"tìm"}, "san": {"sản"}, "pham": {"phẩm"}, "loai": {"loại"}, "hang": {"hàng"},
    "nhu": {"như"}, "nay": {"này", "nay"}, "hom": {"hôm"}, "muon": {"muốn"}, "tren": {"trên"}, "cac": {"các"},
    "nhung": {"những", "nhưng"}, "se": {"sẽ"}, "rat": {"rất"}, "qua": {"quá"}, "hoac": {"hoặc"}, "neu": {"nếu"},
    "thi": {"thì"}, "di": {"đi"}, "vao": {"vào"}, "phai": {"phải"}, "ap": {"áp"}, "va": {"và"}, "la": {"là"},
    "vay": {"vậy"}, "nhe": {"nhé"}, "nhi": {"nhỉ"}, "oi": {"ơi"}, "ben": {"bên"}, "bao": {"bao"}, "mon": {"món"}, "cai": {"cái"}, "chiec": {"chiếc"}, "no": {"nó", "no"},
}
# Accented question words whose unaccented spelling is a product word (tủ, đèn, tải).
STOP_ACCENTED = {"mất", "từ", "đến", "tại"}
# Spoken form -> the form used in the documents (checked on normalized text).
ALIASES = {"thanh pho ho chi minh": "tp hcm", "sai gon": "tp hcm", "ho chi minh": "tp hcm"}

# Words that ask about the catalogue itself ("which products do you sell?"). Only used when no content word remains.
CATALOG_PAIRS = {("san", "pham"), ("mat", "hang"), ("hang", "hoa")}
CATALOG_WORDS = {"product", "products", "catalog", "catalogue", "items"}
# A question about stock asks for a stored figure. A catalogue of descriptions that never gives one cannot answer it,
# however many other words of the question (product name, size) the description happens to share.
# The same holds for offers (a stated discount or code), and for private data or actions on an order, which a public
# assistant must only explain by POLICY, never perform or look up. Phrases are folded words, matched as a sequence; they
# are language cues, not product names. ("available" is deliberately not a stock cue: "which sizes are available?" asks
# for a list, not a figure.)
DATA_PHRASES = {
    "stock": [("con", "hang"), ("het", "hang"), ("ton", "kho"), ("trong", "kho"), ("hang", "moi", "ve"), ("stock",),
              ("inventory",), ("restock",), ("sold", "out")],
    "offer": [("khuyen", "mai"), ("giam", "gia"), ("uu", "dai"), ("tang", "kem"), ("ma", "giam"), ("voucher",), ("coupon",),
              ("discount",), ("promo",), ("promotion",), ("sale",), ("freeship",), ("free", "ship"), ("black", "friday")],
    "private": [("don", "hang", "cua", "toi"), ("trang", "thai", "don"), ("so", "dien", "thoai"), ("dia", "chi", "cua", "khach"),
                ("thong", "tin", "khach"), ("order", "status"), ("track", "my", "order"), ("my", "order"),
                ("hoan", "tien", "cho"), ("huy", "don"), ("xac", "nhan", "don"), ("refund", "me"), ("cancel", "my", "order")],
}
POLICY_CATEGORIES = {"policy", "operations"}   # documents that describe rules and procedures rather than hold data
STOCK_CUES_IN_DOCS = {"stock", "inventory", "kho", "ton"}
OFFER_CUES_IN_DOCS = {"giam", "khuyen", "uu", "tang", "discount", "sale", "voucher", "coupon", "off", "promo"}


def asks_for(kind: str, folded: list[str]) -> bool:
    return any(tuple(folded[i:i + len(p)]) == p for p in DATA_PHRASES[kind] for i in range(len(folded) - len(p) + 1))


def _near_number(tokens: list[str], cues, window: int) -> bool:
    return any(t in cues and any(tokens[j].isdigit() for j in range(max(0, i - window), min(len(tokens), i + window + 1)))
               for i, t in enumerate(tokens))


def states_stock(tokens: list[str], window: int = 3) -> bool:
    """True when a document gives a stock figure: a stock word with a number right next to it."""
    return _near_number(tokens, STOCK_CUES_IN_DOCS, window)


def states_offer(tokens: list[str], window: int = 4) -> bool:
    """True when a document states a concrete offer: a discount word with a number (a rate or an amount) close to it."""
    return _near_number(tokens, OFFER_CUES_IN_DOCS, window)


# "It", "that one", "the second one": words that point at something said before. A question made only of such a pointer
# and an attribute ("how much is that one?") has no subject of its own; searching with just the attribute would return
# every priced document. Without a previous turn to resolve the pointer the search must not run.
CLASSIFIERS = {("cai",), ("mau",), ("mon",), ("loai",), ("chiec",), ("san", "pham")}
ORDINAL_WORDS = {"nhat": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4}
DEMONSTRATIVES = {"nay", "do", "kia"}
ENGLISH_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1}


def _pointer(items):
    """('pronoun'|'ordinal', n or None, words) when the question points at something said before, else None.

    "nó", "cái đó", "sản phẩm này", "it", "that one" and "cái thứ hai", "mẫu đầu tiên", "the last one". An ordinal needs
    a classifier ("cái", "mẫu", ...) because "thứ hai" alone is also Monday, and "đơn đầu tiên" is not "the first one".
    `words` are the folded words of the pointer phrase; they are references, not things to look for.
    """
    folded = [f for _, f, _ in items]
    n = len(folded)
    for i in range(n):
        for classifier in CLASSIFIERS:
            width = len(classifier)
            if tuple(folded[i:i + width]) != classifier or i + width >= n:
                continue
            nxt = folded[i + width:i + width + 3]
            if nxt[0] == "thu" and len(nxt) > 1 and nxt[1] in ORDINAL_WORDS:
                return "ordinal", ORDINAL_WORDS[nxt[1]], set(classifier) | {"thu", nxt[1]}
            if nxt[0] == "dau":
                return "ordinal", 1, set(classifier) | {"dau", "tien"}
            if nxt[0] == "cuoi":
                return "ordinal", -1, set(classifier) | {"cuoi", "cung"}
            if nxt[0] in DEMONSTRATIVES:
                return "pronoun", None, set(classifier) | {nxt[0]}
    for i, f in enumerate(folded):
        if f in ENGLISH_ORDINALS and i + 1 < n and folded[i + 1] in {"one", "product", "item"}:
            return "ordinal", ENGLISH_ORDINALS[f], {f, folded[i + 1]}
        if f in {"this", "that"} and i + 1 < n and folded[i + 1] in {"one", "product", "item"}:
            return "pronoun", None, {f, folded[i + 1]}
        if f == "it":
            return "pronoun", None, {"it"}
    if any(raw == "nó" for raw, _, _ in items):
        return "pronoun", None, {"no"}
    return None


# "What are its features / details / description?": the frame of a request for information, not words to find in a document.
FRAME_PAIRS = {("dac", "diem"), ("dac", "tinh"), ("thong", "tin"), ("chi", "tiet"), ("mo", "ta"), ("tinh", "nang")}

# Cues of a "what do you have?" question (used to prefer documents whose TITLE names the thing asked about).
DISCOVERY_FOLDED = {"nao", "gi", "loai", "nhung"}
DISCOVERY_RAW = {"bán"}


class Lexicon:
    """Spellings used by the indexed documents: folded token -> raw spellings, and document frequency."""

    def __init__(self, texts, known=(), titles=()):
        self.raws: dict[str, dict[str, int]] = {}   # folded token -> {typed spelling: occurrences}
        self.df: dict[str, int] = {}
        # Words that NAME things: they occur in a few document titles. A word repeated in many titles ("giả lập",
        # "demo") is a label shared by the whole catalogue, not a name; one that is in no title describes a thing.
        titles = list(titles)
        in_titles: dict[str, int] = {}
        raw_in_titles: dict[str, int] = {}
        for title in titles:
            for w in set(normalize(title).split()):
                in_titles[w] = in_titles.get(w, 0) + 1
            for r in set(raw_tokens(title)):
                raw_in_titles[r] = raw_in_titles.get(r, 0) + 1
        cap = max(2, 0.3 * len(titles))
        self.title_words = {w for w, n in in_titles.items() if n <= cap} - STOP
        self.title_raw_words = {r for r, n in raw_in_titles.items() if n <= cap}

        self.known = set(known)   # words the search layer understands without the documents (domain synonyms)
        texts = list(texts)
        self.size = len(texts)
        for text in texts:
            seen = set()
            for raw in raw_tokens(text):
                for piece in normalize(raw).split():
                    self.raws.setdefault(piece, {}).setdefault(raw, 0)
                    self.raws[piece][raw] += 1
                    seen.add(piece)
            for piece in seen:
                self.df[piece] = self.df.get(piece, 0) + 1

    def names_a_thing(self, folded: str, typed: str) -> bool:
        """Is this query word one of the words that name a thing? Typed with diacritics it must match them too."""
        return typed in self.title_raw_words if typed != folded else folded in self.title_words

    def has_other_reading(self, folded: str, function_forms) -> bool:
        """True when the documents use this spelling mostly in a reading other than the function word's."""
        counts = self.raws.get(folded, {})
        other = sum(n for raw, n in counts.items() if raw not in function_forms)
        return other > 0 and other >= sum(n for raw, n in counts.items() if raw in function_forms)

    def correct(self, token: str) -> str | None:
        """Nearest indexed (or stop) word for a token the corpus has never seen; None when unsure."""
        if len(token) < 3 or any(c.isdigit() for c in token) or token in self.df or token in STOP or token in self.known:
            return None
        limit = 1 if len(token) < 8 else 2
        best, tied = limit + 1, []
        for cand in list(self.df) + list(STOP):
            if abs(len(cand) - len(token)) > limit:
                continue
            d = _osa(token, cand)
            if d < best:
                best, tied = d, [cand]
            elif d == best and cand not in tied:
                tied.append(cand)
        if best > limit or len(tied) != 1:
            return None
        if len(token) < 6 and sorted(token) != sorted(tied[0]):
            return None   # a short word is only repaired when it is a transposition of a known word
        return tied[0]


_KEY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_KEY_OFFSET = (0.0, 0.25, 0.75)


def _adjacent_keys(a: str, b: str) -> bool:
    """Neighbouring keys on a QWERTY keyboard (the only substitution that looks like a slip of the finger)."""
    def pos(ch):
        for row, keys in enumerate(_KEY_ROWS):
            if ch in keys:
                return keys.index(ch) + _KEY_OFFSET[row], row
        return None
    pa, pb = pos(a), pos(b)
    return bool(pa and pb and a != b and abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1)


def _osa(a: str, b: str) -> int:
    """Typo distance: insert, delete, swap neighbours, or replace a letter by a neighbouring key.

    Any other substitution is not a typo ("khuyen" -> "chuyen" is a different word), so it costs more than any limit.
    """
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else (1 if _adjacent_keys(a[i - 1], b[j - 1]) else 99)
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


@dataclass
class Analysis:
    terms: list[str] = field(default_factory=list)       # content words every gate checks
    soft: list[str] = field(default_factory=list)        # ambiguous spellings: searched, but not required
    dropped: list[tuple[str, str]] = field(default_factory=list)
    corrections: dict[str, str] = field(default_factory=dict)
    accented: dict[str, str] = field(default_factory=dict)
    discovery: bool = False
    catalog: bool = False
    promoted: bool = False
    asks_stock: bool = False
    asks_offer: bool = False                              # "any discount?": needs a stated offer in the document
    asks_private: bool = False                            # order status, phone numbers, refunds: policy documents only
    needs_referent: bool = False                          # "how much is that one?": the subject is only a pointer
    pointer: tuple | None = None                          # ('pronoun', None) | ('ordinal', n) found in the question
    names: list[str] = field(default_factory=list)       # unknown proper names / model codes in the question
    quantities: list = field(default_factory=list)       # numbers with units that must be stated exactly
    conditions: list = field(default_factory=list)       # comparisons computed from the documents' numbers

    def trace(self) -> dict:
        return {"terms": self.terms, "soft_terms": self.soft, "corrections": self.corrections,
                "dropped": [w for w, _ in self.dropped], "asks_stock": self.asks_stock,
                "asks_offer": self.asks_offer, "asks_private": self.asks_private,
                "needs_referent": self.needs_referent, "pointer": list(self.pointer) if self.pointer else None,
                "names": self.names, "quantities": [f"{q.value:g} {q.unit}" for q in self.quantities],
                "conditions": [c.text for c in self.conditions],
                "intent": "catalog" if self.catalog else "discovery" if self.discovery else "lookup"}


def _role(raw: str, folded: str, lexicon: Lexicon) -> str:
    """'function' (dropped), 'content' (required) or 'soft' (ambiguous spelling)."""
    if raw in STOP_ACCENTED:
        return "function"
    if folded not in STOP:
        return "content"
    forms = FUNCTION_FORMS.get(folded)
    if forms is None or raw in forms:
        return "function"
    if raw != folded:
        return "content"
    return "soft" if lexicon.has_other_reading(folded, forms) else "function"


def _items(query: str):
    """(typed form, folded form, as written) per word, with spoken aliases replaced by the form the documents use."""
    items = []
    cased = re.findall(r"\w+", unicodedata.normalize("NFC", query))
    for index, raw in enumerate(raw_tokens(query)):
        written = cased[index] if index < len(cased) else raw
        pieces = normalize(raw).split()
        items.extend([(raw, pieces[0], written)] if len(pieces) == 1 else [(p, p, p) for p in pieces])
    folded = [f for _, f, _ in items]
    for alias, canonical in ALIASES.items():
        words, i = alias.split(), 0
        while i <= len(folded) - len(words):
            if folded[i:i + len(words)] == words:
                repl = canonical.split()
                items[i:i + len(words)] = [(w, w, w) for w in repl]
                folded = [f for _, f, _ in items]
                i += len(repl)
            else:
                i += 1
    return items


def _looks_like_a_name(written: str, position: int, shouting: bool) -> bool:
    """A word that names something: Capitalised inside the sentence, camelCase, or letters mixed with digits."""
    if written.isdigit() or shouting:
        return False
    letters, digits = any(c.isalpha() for c in written), any(c.isdigit() for c in written)
    if letters and digits:
        return written[0].isalpha()     # model codes (X7, RTX3060); "120cm", "11oz", "5V" are quantities
    return letters and ((position > 0 and written[:1].isupper() and not written.isupper())
                        or any(c.isupper() for c in written[1:]) and not written.isupper())


def analyze(query: str, lexicon: Lexicon) -> Analysis:
    result = Analysis()
    # Comparison phrases ("dưới 2 triệu") are conditions to compute, not words to find: cut them out first.
    result.conditions, query = parse_conditions(query)
    result.quantities = extract(query)
    items = _items(query)
    folded_all = [f for _, f, _ in items]
    result.catalog = (any(p in CATALOG_PAIRS for p in zip(folded_all, folded_all[1:]))
                      or any(f in CATALOG_WORDS for f in folded_all))
    result.discovery = any(f in DISCOVERY_FOLDED or r in DISCOVERY_RAW for r, f, _ in items)
    result.asks_stock = asks_for("stock", folded_all)
    result.asks_offer = asks_for("offer", folded_all)
    result.asks_private = asks_for("private", folded_all)
    letters = [c for c in query if c.isalpha()]
    shouting = bool(letters) and all(c.isupper() for c in letters)
    fixes = 0
    frame = {i + k for i in range(len(folded_all) - 1) if (folded_all[i], folded_all[i + 1]) in FRAME_PAIRS for k in (0, 1)}
    for position, (raw, folded, written) in enumerate(items):
        if position in frame:
            result.dropped.append((raw, "request frame"))
            continue
        corrected = False
        if folded not in lexicon.df and folded not in STOP and fixes < MAX_CORRECTIONS:   # correct() skips known words
            fixed = lexicon.correct(folded)
            if fixed:
                result.corrections[raw] = fixed
                raw = folded = fixed
                corrected, fixes = True, fixes + 1
        if len(folded) < 2 and not folded.isdigit():
            result.dropped.append((raw, "too short"))
            continue
        role = "function" if corrected and folded in STOP else _role(raw, folded, lexicon)
        if role == "function":
            result.dropped.append((raw, "function word"))
        elif role == "soft":
            result.soft.append(folded)
        else:
            result.terms.append(folded)
            if raw != folded and not corrected:
                result.accented[folded] = raw
            if (not corrected and folded not in lexicon.df and folded not in lexicon.known
                    and _looks_like_a_name(written, position, shouting)):
                result.names.append(folded)   # a name the catalogue has never seen: it must be matched, not guessed
    result.names = list(dict.fromkeys(result.names))
    result.terms = list(dict.fromkeys(result.terms))[:MAX_TERMS]
    result.soft = [t for t in dict.fromkeys(result.soft) if t not in result.terms]
    if not result.terms and result.soft:
        result.terms, result.soft, result.promoted = result.soft, [], True
    pointer = _pointer(items)
    if pointer:
        result.pointer = pointer[:2]
        result.terms = [t for t in result.terms if t not in pointer[2]]     # references, not things to look for
        result.soft = [t for t in result.soft if t not in pointer[2]]
        # "how much is that one?", "does it have a lock?": what is left describes a thing. If it names one (a word of some
        # title: "Bàn Oak này"), the question has its own subject and needs no earlier turn.
        result.needs_referent = not any(lexicon.names_a_thing(t, result.accented.get(t, t)) for t in result.terms)
    return result
