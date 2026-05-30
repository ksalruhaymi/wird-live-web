import ast
import csv
import json
import re
from pathlib import Path

INPUT_CSV = "apps/quran/data/hafs.csv"
OUTPUT_CSV = "apps/quran/data/hafs_positions_improved.csv"

# Adjust if your source image size is different
IMAGE_WIDTH = 1300
IMAGE_HEIGHT = 2200

SURAH_NAME_TO_NUMBER = {
    "سورة الفاتحة": 1,
    "سورة البقرة": 2,
    "سورة آل عمران": 3,
    "سورة النساء": 4,
    "سورة المائدة": 5,
    "سورة الأنعام": 6,
    "سورة الأعراف": 7,
    "سورة الأنفال": 8,
    "سورة التوبة": 9,
    "سورة يونس": 10,
    "سورة هود": 11,
    "سورة يوسف": 12,
    "سورة الرعد": 13,
    "سورة إبراهيم": 14,
    "سورة الحجر": 15,
    "سورة النحل": 16,
    "سورة الإسراء": 17,
    "سورة الكهف": 18,
    "سورة مريم": 19,
    "سورة طه": 20,
    "سورة الأنبياء": 21,
    "سورة الحج": 22,
    "سورة المؤمنون": 23,
    "سورة النور": 24,
    "سورة الفرقان": 25,
    "سورة الشعراء": 26,
    "سورة النمل": 27,
    "سورة القصص": 28,
    "سورة العنكبوت": 29,
    "سورة الروم": 30,
    "سورة لقمان": 31,
    "سورة السجدة": 32,
    "سورة الأحزاب": 33,
    "سورة سبإ": 34,
    "سورة فاطر": 35,
    "سورة يس": 36,
    "سورة الصافات": 37,
    "سورة ص": 38,
    "سورة الزمر": 39,
    "سورة غافر": 40,
    "سورة فصلت": 41,
    "سورة الشورى": 42,
    "سورة الزخرف": 43,
    "سورة الدخان": 44,
    "سورة الجاثية": 45,
    "سورة الأحقاف": 46,
    "سورة محمد": 47,
    "سورة الفتح": 48,
    "سورة الحجرات": 49,
    "سورة ق": 50,
    "سورة الذاريات": 51,
    "سورة الطور": 52,
    "سورة النجم": 53,
    "سورة القمر": 54,
    "سورة الرحمن": 55,
    "سورة الواقعة": 56,
    "سورة الحديد": 57,
    "سورة المجادلة": 58,
    "سورة الحشر": 59,
    "سورة الممتحنة": 60,
    "سورة الصف": 61,
    "سورة الجمعة": 62,
    "سورة المنافقون": 63,
    "سورة التغابن": 64,
    "سورة الطلاق": 65,
    "سورة التحريم": 66,
    "سورة الملك": 67,
    "سورة القلم": 68,
    "سورة الحاقة": 69,
    "سورة المعارج": 70,
    "سورة نوح": 71,
    "سورة الجن": 72,
    "سورة المزمل": 73,
    "سورة المدثر": 74,
    "سورة القيامة": 75,
    "سورة الإنسان": 76,
    "سورة المرسلات": 77,
    "سورة النبأ": 78,
    "سورة النازعات": 79,
    "سورة عبس": 80,
    "سورة التكوير": 81,
    "سورة الإنفطار": 82,
    "سورة المطففين": 83,
    "سورة الإنشقاق": 84,
    "سورة البروج": 85,
    "سورة الطارق": 86,
    "سورة الأعلى": 87,
    "سورة الغاشية": 88,
    "سورة الفجر": 89,
    "سورة البلد": 90,
    "سورة الشمس": 91,
    "سورة الليل": 92,
    "سورة الضحى": 93,
    "سورة الشرح": 94,
    "سورة التين": 95,
    "سورة العلق": 96,
    "سورة القدر": 97,
    "سورة البينة": 98,
    "سورة الزلزلة": 99,
    "سورة العاديات": 100,
    "سورة القارعة": 101,
    "سورة التكاثر": 102,
    "سورة العصر": 103,
    "سورة الهمزة": 104,
    "سورة الفيل": 105,
    "سورة قريش": 106,
    "سورة الماعون": 107,
    "سورة الكوثر": 108,
    "سورة الكافرون": 109,
    "سورة النصر": 110,
    "سورة المسد": 111,
    "سورة الإخلاص": 112,
    "سورة الفلق": 113,
    "سورة الناس": 114,
}


def parse_polygon(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    try:
        return json.loads(value)
    except Exception:
        try:
            return ast.literal_eval(value)
        except Exception:
            return []


def extract_page_number(file_path, page_value):
    if page_value not in (None, "", -1, "-1"):
        try:
            return int(page_value)
        except Exception:
            pass

    match = re.search(r"(\d+)\.(?:webp|png|jpg|jpeg)$", str(file_path), re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def normalize_box(box):
    x = float(box.get("x", 0))
    y = float(box.get("y", 0))
    w = float(box.get("width", 0))
    h = float(box.get("height", 0))
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
    }


def filter_tiny_boxes(boxes, min_width=20, min_height=12, min_area=500):
    cleaned = []
    for box in boxes:
        w = box["width"]
        h = box["height"]
        area = w * h
        if w >= min_width and h >= min_height and area >= min_area:
            cleaned.append(box)
    return cleaned


def same_line(box1, box2, y_tolerance=28):
    c1 = box1["y"] + (box1["height"] / 2)
    c2 = box2["y"] + (box2["height"] / 2)
    return abs(c1 - c2) <= y_tolerance


def merge_two_boxes(box1, box2):
    x1 = min(box1["x"], box2["x"])
    y1 = min(box1["y"], box2["y"])
    x2 = max(box1["x"] + box1["width"], box2["x"] + box2["width"])
    y2 = max(box1["y"] + box1["height"], box2["y"] + box2["height"])
    return {
        "x": x1,
        "y": y1,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def merge_close_boxes_in_same_line(boxes, gap_tolerance=35, y_tolerance=28):
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: (b["y"], b["x"]))
    lines = []

    for box in boxes:
        placed = False
        for line in lines:
            if same_line(line[0], box, y_tolerance=y_tolerance):
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])

    merged_boxes = []

    for line in lines:
        line = sorted(line, key=lambda b: b["x"])
        current = line[0]

        for nxt in line[1:]:
            current_right = current["x"] + current["width"]
            gap = nxt["x"] - current_right

            if gap <= gap_tolerance and same_line(current, nxt, y_tolerance=y_tolerance):
                current = merge_two_boxes(current, nxt)
            else:
                merged_boxes.append(current)
                current = nxt

        merged_boxes.append(current)

    return merged_boxes


def sort_polygon_for_display(boxes):
    return sorted(boxes, key=lambda b: (b["y"], b["x"]))


def to_percent(value, total):
    return round((value / total) * 100, 4)


def polygon_to_percent(boxes):
    result = []
    for box in boxes:
        result.append({
            "x": to_percent(box["x"], IMAGE_WIDTH),
            "y": to_percent(box["y"], IMAGE_HEIGHT),
            "width": to_percent(box["width"], IMAGE_WIDTH),
            "height": to_percent(box["height"], IMAGE_HEIGHT),
        })
    return result


def overall_bounds(boxes):
    if not boxes:
        return 0, 0, 0, 0

    min_x = min(box["x"] for box in boxes)
    min_y = min(box["y"] for box in boxes)
    max_x = max(box["x"] + box["width"] for box in boxes)
    max_y = max(box["y"] + box["height"] for box in boxes)

    return min_x, min_y, max_x - min_x, max_y - min_y


def convert_row(row):
    surah_name = str(row.get("surah_name", "")).strip()
    surah_number = SURAH_NAME_TO_NUMBER.get(surah_name)

    if not surah_number:
        return None

    try:
        ayah_number = int(row.get("ayah_number"))
    except Exception:
        return None

    page_number = extract_page_number(row.get("file"), row.get("page"))
    if not page_number:
        return None

    raw_polygon = parse_polygon(row.get("polygon"))
    raw_boxes = [normalize_box(box) for box in raw_polygon]

    if not raw_boxes:
        return None

    cleaned = filter_tiny_boxes(raw_boxes)
    if not cleaned:
        cleaned = raw_boxes

    improved = merge_close_boxes_in_same_line(cleaned)
    improved = sort_polygon_for_display(improved)

    x, y, width, height = overall_bounds(improved)

    improved_percent = polygon_to_percent(improved)

    return {
        "surah_number": surah_number,
        "ayah_number": ayah_number,
        "page_number": page_number,
        "x": to_percent(x, IMAGE_WIDTH),
        "y": to_percent(y, IMAGE_HEIGHT),
        "width": to_percent(width, IMAGE_WIDTH),
        "height": to_percent(height, IMAGE_HEIGHT),
        "polygon": json.dumps(improved_percent, ensure_ascii=False),
    }


def main():
    input_path = Path(INPUT_CSV)
    output_path = Path(OUTPUT_CSV)

    rows = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            converted = convert_row(row)
            if converted:
                rows.append(converted)

    rows.sort(key=lambda r: (r["page_number"], r["surah_number"], r["ayah_number"]))

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "surah_number",
                "ayah_number",
                "page_number",
                "x",
                "y",
                "width",
                "height",
                "polygon",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done: {len(rows)} rows written to {output_path}")


if __name__ == "__main__":
    main()