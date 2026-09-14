import re
from dataclasses import dataclass, field

from unidecode import unidecode

KAZAKH = str.maketrans(
    {
        "ә": "а",
        "ғ": "г",
        "қ": "к",
        "ң": "н",
        "ө": "о",
        "ұ": "у",
        "ү": "у",
        "һ": "х",
        "і": "и",
        "ё": "е",
    }
)

NUMBER = re.compile(
    r"(?:№|N°|No\.?|#)\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:-?\s*(?:ші|шы|ыншы|інші))?\s*(?:мектеп|школ)",
    re.IGNORECASE,
)

TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("complex_kg", re.compile(r"детск\w*\s+сад|ясли|балабакша|сад-|бакша", re.I)),
    ("evening", re.compile(r"вечерн|сменн", re.I)),
    ("special", re.compile(r"интернат|специальн\w*\s+(?:школ|коррекц)|коррекц", re.I)),
    ("college", re.compile(r"колледж|college|проф\w*\s*лице|профлице|кәсіптік|касиптик", re.I)),
    (
        "nis",
        re.compile(
            r"назарбаев\s+интеллект|назарбаев\s+зияткер|\bниш\b|nazarbayev intellectual", re.I
        ),
    ),
    ("rfmsh", re.compile(r"физико-математ|физика-математика|\bрфмш\b", re.I)),
    ("international", re.compile(r"международн|international|халыкаралык", re.I)),
    ("gymnasium", re.compile(r"гимназ", re.I)),
    ("lyceum", re.compile(r"лице[йяи]", re.I)),
    ("general", re.compile(r"школ|мектеп|жоббм|school", re.I)),
]

GENERAL_FAMILY = {"general", "gymnasium", "lyceum"}

BOILERPLATE = {
    "государственное",
    "государтвенное",
    "учереждение",
    "учреждение",
    "учреждения",
    "коммунальное",
    "акимата",
    "акимат",
    "города",
    "городы",
    "город",
    "г",
    "астаны",
    "астана",
    "управления",
    "управление",
    "образования",
    "отдела",
    "кгу",
    "гу",
    "ру",
    "товарищество",
    "ограниченной",
    "ответственностью",
    "тоо",
    "филиал",
    "некоммерческое",
    "некоммерческого",
    "акционерного",
    "общества",
    "нао",
    "ао",
    "мемлекеттик",
    "мекемеси",
    "мекеме",
    "коммуналдык",
    "каласы",
    "каласынын",
    "акимдигинин",
    "билим",
    "баскармасынын",
    "боlimинин",
    "имени",
    "им",
    "атындагы",
    "ат",
    "средняя",
    "средней",
    "общеобразовательная",
    "жалпы",
    "орта",
    "беретин",
    "школа",
    "школы",
    "мектеп",
    "мектеби",
    "мектебі",
    "гимназия",
    "гимназии",
    "лицей",
    "лицея",
    "лицейи",
    "жоббм",
    "school",
    "автономной",
    "организации",
    "организация",
    "образовательная",
    "оф",
    "фонд",
    "фонда",
    "объединение",
    "центр",
    "комплекс",
    "и",
}


STEM_STOP = {
    "жауап",
    "серик",
    "серiк",
    "шекте",
    "когам",
    "емес",
    "комме",
    "уйым",
    "уйымы",
    "дербе",
    "беру",
    "калас",
    "филиа",
    "мекте",
    "баска",
    "акимд",
    "билим",
    "мемле",
    "комму",
    "автон",
    "общео",
    "неком",
    "акцио",
    "общес",
    "учреж",
    "госуд",
    "город",
    "астан",
    "столи",
    "частн",
    "респу",
    "минис",
    "казак",
    "казах",
    "ултты",
    "нацио",
    "кмм",
    "маман",
    "специ",
    "арнай",
    "арнал",
    "интер",
    "балаб",
    "кешен",
    "непре",
    "уздик",
    "между",
    "халык",
    "интел",
    "зиятк",
    "назар",
    "багыт",
    "напра",
    "колле",
}


@dataclass
class ParsedName:
    raw: str
    normalized: str
    number: int | None
    kind: str
    tokens: list[str] = field(default_factory=list)
    latin: str = ""


def normalize(text: str) -> str:
    value = str(text or "").lower().translate(KAZAKH)
    value = re.sub(r"[«»\"'“”„`´]", " ", value)
    value = re.sub(r"(?<=\w)-(?=\s)|(?<=\s)-(?=\w)", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_number(text: str) -> int | None:
    for match in NUMBER.finditer(text):
        value = match.group(1) or match.group(2)
        if value:
            number = int(value)
            if 0 < number < 400:
                return number
    return None


def classify(text: str) -> str:
    for kind, pattern in TYPE_RULES:
        if pattern.search(text):
            return kind
    return "other"


def stem_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zа-я]+", text)
    stems = []
    for word in words:
        if word in BOILERPLATE or len(word) < 3:
            continue
        stem = word[:5]
        if stem in STEM_STOP:
            continue
        stems.append(stem)
    return stems


def parse(*variants: str | None) -> ParsedName:
    texts = [v for v in variants if v and str(v).strip() and str(v).lower() != "nan"]
    joined = " | ".join(normalize(t) for t in texts)
    number = None
    for text in texts:
        number = extract_number(normalize(text))
        if number is not None:
            break
    kind = classify(joined)
    body = re.sub(r"(?:№|n°|no\.?|#)\s*\d{1,3}", " ", joined)
    tokens = sorted(set(stem_tokens(body)))
    return ParsedName(
        raw=texts[0] if texts else "",
        normalized=joined,
        number=number,
        kind=kind,
        tokens=tokens,
        latin=unidecode(" ".join(tokens)),
    )


def kinds_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    if a in GENERAL_FAMILY and b in GENERAL_FAMILY:
        return True
    return "other" in (a, b)
