"""Chain / franchise detection. Branches of national chains are not prospects:
the website and marketing are decided at head office, not by whoever answers
the branch phone."""

from __future__ import annotations

import re

# Brands with many branches in Bulgaria (Latin and Cyrillic spellings), matched as
# whole words in the business name. Only unambiguous brand names: common words and
# first names ("Happy", "Лили", "Еко", "Зора") are left out on purpose, because small
# independent businesses use them too.
CHAIN_BRANDS = [
    # retail & groceries
    "lidl", "лидл", "kaufland", "кауфланд", "billa", "fantastico", "фантастико", "t market", "т маркет",
    "dm drogerie", "sopharmacy", "софармаси", "subra", "субра", "marvi", "марви", "remedium", "ремедиум",
    "technopolis", "технополис", "technomarket", "техномаркет", "praktiker", "практикер", "bricolage",
    "бриколаж", "ikea", "икеа", "pepco", "пепко", "decathlon", "декатлон", "jysk", "lafka", "лафка",
    # fuel & auto chains
    "shell", "omv", "омв", "lukoil", "лукойл", "rompetrol", "vianor", "euromaster", "евромастер",
    "bosch car service", "intercars", "интеркарс",
    # food chains
    "mcdonald's", "mcdonalds", "макдоналдс", "kfc", "starbucks", "старбъкс", "costa coffee", "domino's",
    "dominos", "доминос", "telepizza", "телепица", "subway", "burger king", "бургер кинг", "dunkin",
    "happy bar", "хепи бар",
    # telecom, couriers, banks, insurers
    "yettel", "йетел", "vivacom", "виваком", "speedy", "спиди", "econt", "еконт", "dhl", "unicredit",
    "уникредит", "postbank", "пощенска банка", "fibank", "raiffeisen", "райфайзен", "allianz", "алианц",
    "bulstrad", "булстрад", "bulins", "булинс", "easypay", "изипей",
    # fitness chains
    "pulse fitness", "пулс фитнес", "sport depot", "спорт депо",
    # clinics & labs
    "cibalab", "цибалаб", "ramus", "рамус", "synevo", "синево", "acibadem", "аджибадем", "tokuda", "токуда",
]  # fmt: skip

_CHAIN_RE = re.compile(
    r"(?<![\w])("
    + "|".join(re.escape(b) for b in sorted(CHAIN_BRANDS, key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)

# The same own-website domain on this many listings means branches of one company.
SHARED_DOMAIN_CHAIN_THRESHOLD = 3


def chain_brand(name: str | None) -> str | None:
    """The chain brand found in a business name, if any."""
    if not name:
        return None
    match = _CHAIN_RE.search(name)
    return match.group(1) if match else None
