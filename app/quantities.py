"""Numbers with units: what a question asks for exactly, what it compares, and what a document states.

Comparisons ("dưới 2 triệu", "cao hơn 70 cm") are decided here, in code, from numbers found in the document text.
Neither an embedding score nor a language model takes part in that decision. When the document does not state the
attribute clearly the answer is "unknown", never "yes".
"""
import math
import re
import unicodedata
from dataclasses import dataclass

NUM = r"\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?"

# (family, unit, multiplier to the base unit of the family, spellings). Longest spellings first inside a family.
_UNITS = [
    ("money", "vnd", 1e6, ["triệu", "trieu", "tr"]),
    ("money", "vnd", 1e3, ["nghìn", "nghin", "ngàn", "ngan", "k"]),
    ("money", "vnd", 1.0, ["vnd", "vnđ", "đồng", "dong", "đ"]),
    ("money", "usd", 1.0, ["usd", "dollars", "dollar", "$"]),
    ("length", "cm", 1.0, ["centimeters", "centimeter", "centimet", "cm"]),
    ("length", "cm", 0.1, ["mm"]),
    ("length", "cm", 100.0, ["mét", "met", "m"]),
    ("percent", "%", 1.0, ["phần trăm", "percent", "%"]),
    ("time", "day", 1.0, ["ngày", "ngay", "days", "day"]),
    ("time", "week", 1.0, ["tuần", "tuan", "weeks", "week"]),
    ("time", "month", 1.0, ["tháng", "thang", "months", "month"]),
    ("time", "year", 1.0, ["năm", "nam", "years", "year"]),
    ("time", "hour", 1.0, ["giờ", "gio", "tiếng", "tieng", "hours", "hour"]),
    ("weight", "g", 1000.0, ["kg"]),
    ("weight", "g", 1.0, ["g"]),
    ("volume", "ml", 1.0, ["ml"]),
    ("volume", "oz", 1.0, ["oz"]),
]
_UNIT_BY_WORD = {w: (fam, unit, mult) for fam, unit, mult, words in _UNITS for w in words}
_UNIT_ALT = "|".join(re.escape(w) for w in sorted(_UNIT_BY_WORD, key=len, reverse=True))
_DIMS = rf"(?P<dims>(?:{NUM})(?:\s*[x×*]\s*(?:{NUM}))+)\s*(?P<dunit>{_UNIT_ALT})(?!\w)"
_SINGLE = rf"(?P<num>{NUM})\s*(?P<unit>{_UNIT_ALT})(?!\w)"
_PREFIX_CUR = rf"(?P<cur>usd|\$)\s*(?P<pnum>{NUM})"
_RANGE_Q = rf"(?P<rng>(?:{NUM})\s*[-–—]\s*(?:{NUM}))\s*(?P<runit>{_UNIT_ALT})(?!\w)"    # "72–118 cm"
_QUANTITY = re.compile(f"{_DIMS}|{_RANGE_Q}|{_PREFIX_CUR}|{_SINGLE}", re.I)


def _fold(word: str) -> str:
    word = word.replace("đ", "d").replace("Đ", "D")
    word = unicodedata.normalize("NFKD", word)
    return "".join(c for c in word if not unicodedata.combining(c)).lower()


def parse_number(text: str) -> float:
    """'1.890.000' and '390,000' are thousands; '18.00' and '1,5' are decimals."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        return float(re.sub(r"[.,]", "", text))
    return float(text.replace(",", "."))


@dataclass(frozen=True)
class Quantity:
    value: float            # in the base unit of its family (VND, USD, cm, ...)
    family: str
    unit: str
    labels: tuple = ()      # up to five folded words written just before the number ("chieu", "cao")
    in_dimensions: bool = False   # one of "A x B x C cm": which side is meant is not stated
    start: int = 0
    end: int = 0


def _labels(text: str, start: int) -> tuple:
    """Words written before the number, up to the previous number, so that "cao 75 cm, rộng 60 cm" labels each value."""
    labels = []
    for word in reversed(re.findall(r"\w+", text[:start])):
        if word.isdigit() or len(labels) == 5:
            break
        labels.append(_fold(word))
    return tuple(reversed(labels))


def extract(text: str) -> list[Quantity]:
    found = []
    for m in _QUANTITY.finditer(text):
        if m.group("dims"):
            fam, unit, mult = _UNIT_BY_WORD[m.group("dunit").lower()]
            for n in re.findall(NUM, m.group("dims")):
                found.append(Quantity(parse_number(n) * mult, fam, unit, _labels(text, m.start()), True, m.start(), m.end()))
        elif m.group("rng"):
            fam, unit, mult = _UNIT_BY_WORD[m.group("runit").lower()]
            for n in re.findall(NUM, m.group("rng")):    # both ends carry the label written before the range
                found.append(Quantity(parse_number(n) * mult, fam, unit, _labels(text, m.start()), False, m.start(), m.end()))
        elif m.group("cur"):
            fam, unit, mult = _UNIT_BY_WORD[m.group("cur").lower()]
            found.append(Quantity(parse_number(m.group("pnum")) * mult, fam, unit, _labels(text, m.start()), False, m.start(), m.end()))
        else:
            fam, unit, mult = _UNIT_BY_WORD[m.group("unit").lower()]
            found.append(Quantity(parse_number(m.group("num")) * mult, fam, unit, _labels(text, m.start()), False, m.start(), m.end()))
    return found


SCENARIO_WORDS = {"don", "mua", "dat", "tong", "tri"}   # "đơn 2 triệu", "mua 4 triệu", "trị giá", "tổng": an order's size


def cut_scenario_amounts(text: str):
    """Money amounts that describe the customer's situation ("đơn 2 triệu") rather than a fact to look up.

    They are parameters of the question ("what happens for an order this size?"), not claims the documents must repeat,
    so they are cut out of the question. Returns the question without them.
    """
    spans = [(q.start, q.end) for q in extract(text) if q.family == "money" and SCENARIO_WORDS & set(q.labels[-3:])]
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return text


# ---- comparison conditions ------------------------------------------------------------------------------------------
_LT = ["không quá", "khong qua", "tối đa", "toi da", "ít hơn", "it hon", "nhỏ hơn", "nho hon", "thấp hơn", "thap hon", "dưới", "duoi",
       "under", "below", "less than", "at most", "up to"]
_GT = ["tối thiểu", "toi thieu", "ít nhất", "it nhat", "lớn hơn", "lon hon", "nhiều hơn", "nhieu hon", "trên", "tren",
       "hơn", "hon", "over", "above", "more than", "at least"]
_INCLUSIVE = {"không quá", "khong qua", "tối đa", "toi da", "at most", "up to", "tối thiểu", "toi thieu", "ít nhất",
              "it nhat", "at least"}
_ATTR = ["rộng", "rong", "cao", "dài", "dai", "dày", "day", "sâu", "sau", "nặng", "nang", "đắt", "dat", "rẻ", "re", "giá", "gia"]
_OPS = "|".join(re.escape(w) for w in sorted(_LT + _GT, key=len, reverse=True))
_ATTRS = "|".join(re.escape(w) for w in sorted(_ATTR, key=len, reverse=True))
_COMPARE = re.compile(rf"(?:(?P<attr>{_ATTRS})\s+)?(?P<op>{_OPS})\s+(?P<num>{NUM})\s*(?P<unit>{_UNIT_ALT})(?!\w)", re.I)
_RANGE = re.compile(rf"(?:từ|tu|between)\s+(?P<a>{NUM})\s*(?P<ua>{_UNIT_ALT})?\s*(?:đến|den|tới|toi|and|-|–)\s*"
                    rf"(?P<b>{NUM})\s*(?P<unit>{_UNIT_ALT})(?!\w)", re.I)
_LENGTH_ATTRS = {"rong", "cao", "dai", "day", "sau"}


@dataclass(frozen=True)
class Condition:
    family: str
    unit: str
    op: str                 # '<', '<=', '>', '>=' or 'between'
    lo: float | None
    hi: float | None
    attr: str | None        # folded attribute word: 'rong', 'cao', 'gia', ...
    text: str


def parse_conditions(text: str):
    """Comparison conditions in a question and the question with those phrases cut out."""
    conditions, spans = [], []
    for m in _RANGE.finditer(text):
        fam, unit, mult = _UNIT_BY_WORD[m.group("unit").lower()]
        ua = _UNIT_BY_WORD.get((m.group("ua") or "").lower(), (fam, unit, mult))
        a, b = parse_number(m.group("a")) * ua[2], parse_number(m.group("b")) * mult
        conditions.append(Condition(fam, unit, "between", min(a, b), max(a, b), None, m.group(0)))
        spans.append(m.span())
    for m in _COMPARE.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        op_word = m.group("op").lower()
        attr = _fold(m.group("attr") or "") or None
        fam, unit, mult = _UNIT_BY_WORD[m.group("unit").lower()]
        value = parse_number(m.group("num")) * mult
        lower = op_word in _LT
        if attr == "re":
            lower = True       # "rẻ hơn X" = cheaper than X
        inclusive = op_word in _INCLUSIVE
        op = ("<=" if inclusive else "<") if lower else (">=" if inclusive else ">")
        if attr in {"dat", "re"}:
            attr = "gia"
        conditions.append(Condition(fam, unit, op, None if lower else value, value if lower else None, attr, m.group(0)))
        spans.append(m.span())
    cleaned = text
    for start, end in sorted(spans, reverse=True):
        cleaned = cleaned[:start] + " " + cleaned[end:]
    return conditions, cleaned


def _holds(cond: Condition, v: float) -> bool:
    if cond.op == "between":
        return cond.lo <= v <= cond.hi
    if cond.op == "<":
        return v < cond.hi
    if cond.op == "<=":
        return v <= cond.hi
    return v > cond.lo if cond.op == ">" else v >= cond.lo


def evaluate(cond: Condition, text: str) -> str:
    """'yes' | 'no' | 'unknown' for one document text.

    'no' also covers a document with no number of that kind at all (nothing to show for this question). 'unknown' means
    the document gives numbers of the right kind but not clearly the one asked about (another currency, or sides of
    "120 x 60 cm" without saying which is the width): it must not be presented as satisfying the condition.
    """
    same = [q for q in extract(text) if q.family == cond.family]
    if not same:
        return "no"
    if cond.family == "money":
        usable = [q for q in same if q.unit == cond.unit]
        if not usable:
            return "unknown"                       # e.g. only USD prices for a question in VND
        labelled = [q for q in usable if {"gia", "price"} & set(q.labels)]
        chosen = labelled or (usable if len(usable) == 1 else [])
    else:
        wanted = cond.attr if cond.attr in _LENGTH_ATTRS else None
        labelled = [q for q in same if wanted and wanted in q.labels and not q.in_dimensions]
        chosen = labelled or ([same[0]] if len(same) == 1 and not same[0].in_dimensions and wanted is None else [])
    if not chosen:
        return "unknown"
    verdicts = {_holds(cond, q.value) for q in chosen}
    return "yes" if verdicts == {True} else "no" if verdicts == {False} else "unknown"


def exact_matches(query_quantities: list[Quantity], text: str) -> bool:
    """Every quantity the question names with a unit must be stated, with that unit family, in the text."""
    have = extract(text)
    return all(any(h.family == q.family and h.unit == q.unit and math.isclose(h.value, q.value, rel_tol=1e-9)
                   for h in have) for q in query_quantities)
