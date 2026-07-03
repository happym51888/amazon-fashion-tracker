"""
商品过滤辅助函数

用于统一处理报告和分析阶段的商品排除逻辑。
"""

from __future__ import annotations

import re

TSHIRT_TERMS = [
    "t-shirt",
    "t shirt",
    "tee shirt",
    " tee ",
    "tees",
    "crew neck tee",
    "crewneck tee",
    "crew neck t-shirt",
    "crewneck t-shirt",
    "v-neck tee",
    "v neck tee",
    "v-neck t-shirt",
    "v neck t-shirt",
]

BASIC_TEE_CUES = [
    "solid",
    "plain",
    "basic",
    "essential",
    "everyday",
    "performance",
    "moisture wicking",
    "odor protection",
    "odor protect",
    "dri-power",
    "dri fit",
    "dry fit",
    "classic fit",
    "regular fit",
    "casual",
    "simple",
    "crew neck",
    "crewneck",
    "v-neck",
    "v neck",
    "short sleeve",
    "long sleeve",
    "cotton tee",
    "cotton t-shirt",
    "jersey tee",
    "undershirt",
    "stay tucked",
]

FASHION_TEE_CUES = [
    "graphic",
    "printed",
    "print ",
    "embroidered",
    "embroidery",
    "cropped",
    "crop top",
    "oversized",
    "ribbed",
    "ruffle",
    "lace",
    "mesh",
    "vintage",
    "y2k",
    "boho",
    "washed",
    "distressed",
    "striped",
    "stripe ",
    "floral",
    "plaid",
    "pattern",
    "patterned",
    "sequin",
    "glitter",
    "color block",
    "tie dye",
    "tie-dye",
    "cutout",
    "cut-out",
]

PACK_PATTERNS = [
    r"\b[2-9]\s*-\s*pack\b",
    r"\b[2-9]\s*pack\b",
    r"\bpack of \d+\b",
    r"\bmultipack\b",
    r"\bmulti-pack\b",
]

COLOR_PATTERN = re.compile(
    r"\b(black|white|gray|grey|navy|blue|red|green|pink|beige|brown|purple|yellow|orange|olive|khaki|burgundy|wine|heather|charcoal|cream)\b"
)


def normalize_product_name(product_name: str) -> str:
    return re.sub(r"\s+", " ", (product_name or "").strip().lower())


def is_plain_basic_tshirt(product_name: str) -> bool:
    name = normalize_product_name(product_name)
    if not name:
        return False

    has_tshirt_term = any(term in f" {name} " for term in TSHIRT_TERMS)
    if not has_tshirt_term:
        return False

    if any(term in name for term in FASHION_TEE_CUES):
        return False

    simple_hits = sum(1 for cue in BASIC_TEE_CUES if cue in name)
    color_hits = len(set(COLOR_PATTERN.findall(name)))
    has_pack = any(re.search(pattern, name) for pattern in PACK_PATTERNS)
    has_plain_phrase = any(
        phrase in name
        for phrase in (
            "plain t-shirt",
            "plain tee",
            "solid t-shirt",
            "solid tee",
            "basic tee",
            "basic t-shirt",
            "essential tee",
            "essential t-shirt",
        )
    )

    if has_pack or has_plain_phrase:
        return True
    if simple_hits >= 3:
        return True
    if simple_hits >= 2 and color_hits >= 1:
        return True
    return False


def should_exclude_product(product_name: str, exclude_keywords: list[str]) -> bool:
    name = normalize_product_name(product_name)
    if not name:
        return False
    if any(keyword in name for keyword in exclude_keywords):
        return True
    return is_plain_basic_tshirt(name)
