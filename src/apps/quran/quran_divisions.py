"""
Quran division utilities for Hafs Mushaf (604 pages).

juz-level boundaries are EXACT (derived from ayahs.csv data).
Sub-juz boundaries (hizb, rub3) are proportional within each juz's page range.

Full Quran = 30 juz = 60 hizb = 240 rub3 (quarter-hizb).
Each juz = 8 rub3 units.  All calculations use rub3 as the base unit.
"""
import math

# Exact start/end pages per juz — sourced from ayahs.csv
JUZ_PAGES = {
    1:  (1,   21),  2:  (22,  41),  3:  (42,  61),  4:  (62,  81),
    5:  (82,  101), 6:  (102, 121), 7:  (122, 141), 8:  (142, 161),
    9:  (162, 181), 10: (182, 201), 11: (202, 221), 12: (222, 241),
    13: (242, 261), 14: (262, 281), 15: (282, 301), 16: (302, 321),
    17: (322, 341), 18: (342, 361), 19: (362, 381), 20: (382, 401),
    21: (402, 421), 22: (422, 441), 23: (442, 461), 24: (462, 481),
    25: (482, 501), 26: (502, 521), 27: (522, 541), 28: (542, 561),
    29: (562, 581), 30: (582, 604),
}

# Wird size expressed in rub3 units (1 juz = 8 rub3)
AMOUNT_RUB3_UNITS = {
    "rub3":  1,  "2rub3": 2,  "3rub3": 3,  "hizb":  4,
    "5rub3": 5,  "6rub3": 6,  "7rub3": 7,  "juz":   8,
    "2juz":  16, "3juz":  24, "4juz":  32, "5juz":  40,
    "6juz":  48, "7juz":  56, "8juz":  64, "9juz":  72,
    "10juz": 80,
}

TOTAL_RUB3 = 240  # 30 × 8


def rub3_to_page(rub3_unit: int) -> int:
    """
    Map a 1-based rub3 unit (1–240) to its starting page.
    Exact for juz-level boundaries; proportional within each juz otherwise.
    """
    rub3_unit = max(1, min(rub3_unit, TOTAL_RUB3))
    juz_num = (rub3_unit - 1) // 8 + 1
    pos     = (rub3_unit - 1) % 8          # 0–7 within the juz
    j_start, j_end = JUZ_PAGES[juz_num]
    return j_start + math.floor(pos * (j_end - j_start + 1) / 8)


def total_wirds_for(amount_type: str) -> int:
    units = AMOUNT_RUB3_UNITS.get(amount_type, 8)
    return math.ceil(TOTAL_RUB3 / units)


def wird_page_range(wird_number: int, amount_type: str) -> tuple:
    """
    Return (start_page, end_page) for wird N (1-based).
    """
    units      = AMOUNT_RUB3_UNITS.get(amount_type, 8)
    start_rub3 = (wird_number - 1) * units + 1
    end_rub3   = min(wird_number * units, TOTAL_RUB3)

    if start_rub3 > TOTAL_RUB3:
        return (604, 604)

    start_page = rub3_to_page(start_rub3)
    end_page   = rub3_to_page(end_rub3 + 1) - 1 if end_rub3 < TOTAL_RUB3 else 604

    return (start_page, max(start_page, end_page))
