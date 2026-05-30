from pathlib import Path
import csv
import json
import os

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from core.utils.media import media_url

from identity.rbac.decorators import permission_required
from apps.quran.models import AyahPosition, Qurra
from apps.quran.mushaf_config import (
    DEFAULT_MUSHAF_KEY,
    MUSHAFS,
    get_all_mushaf_dimensions,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "quran/data"
DATA_DIR.mkdir(exist_ok=True)
CSV_PATH = DATA_DIR / "ayahposition.csv"

MAX_SURAH_NUMBER = 114
MAX_PAGE_NUMBER = 604

STUDIO_PERMISSION = "quran_studio.access"


def _clean_mushaf_key(value):
    mushaf_key = str(value or DEFAULT_MUSHAF_KEY).strip().lower()
    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY
    return mushaf_key


def _to_float(value):
    return float(str(value).replace(",", ".").strip())


def _normalize_region(region):
    if not isinstance(region, dict):
        raise ValueError("Each region must be an object")

    required_keys = ("x", "y", "width", "height")
    for key in required_keys:
        if key not in region:
            raise ValueError(f"Missing region field: {key}")

    x = _to_float(region.get("x"))
    y = _to_float(region.get("y"))
    width = _to_float(region.get("width"))
    height = _to_float(region.get("height"))

    if width <= 0 or height <= 0:
        raise ValueError("Region width/height must be greater than zero")

    if x < 0 or y < 0:
        raise ValueError("Region x/y cannot be negative")

    if x > 100 or y > 100:
        raise ValueError("Region x/y cannot exceed 100")

    if width > 100 or height > 100:
        raise ValueError("Region width/height cannot exceed 100")

    if x + width > 100 or y + height > 100:
        raise ValueError("Region exceeds page bounds")

    return {
        "x": float(f"{x:.4f}"),
        "y": float(f"{y:.4f}"),
        "width": float(f"{width:.4f}"),
        "height": float(f"{height:.4f}"),
    }


def _normalize_regions(regions):
    if not isinstance(regions, list) or not regions:
        raise ValueError("Invalid regions")

    normalized = []
    for region in regions:
        normalized.append(_normalize_region(region))

    return normalized


def _regions_from_position(pos):
    regions = []

    for region in (pos.polygon or []):
        try:
            regions.append(_normalize_region(region))
        except (TypeError, ValueError):
            continue

    if regions:
        return regions

    try:
        return [
            _normalize_region({
                "x": pos.x,
                "y": pos.y,
                "width": pos.width,
                "height": pos.height,
            })
        ]
    except (TypeError, ValueError):
        return []


@login_required
@permission_required(STUDIO_PERMISSION)
def ayah_editor(request, page_number: int, mushaf_key=None):
    if page_number <= 0 or page_number > MAX_PAGE_NUMBER:
        return JsonResponse(
            {"status": "error", "message": "Invalid page number"},
            status=400,
        )

    current_mushaf = _clean_mushaf_key(mushaf_key or request.GET.get("mushaf"))
    mushaf = MUSHAFS[current_mushaf].copy()
    mushaf["key"] = current_mushaf
    mushaf["image_prefix"] = media_url(mushaf["image_prefix"].strip("/") + "/")

    page_qs = AyahPosition.objects.filter(
        mushaf_key=current_mushaf,
        page_number=page_number,
    ).order_by("surah_number", "ayah_number")

    last_pos = page_qs.order_by("-surah_number", "-ayah_number").first()

    if last_pos:
        initial_surah = last_pos.surah_number
        initial_ayah = None if last_pos.ayah_number is None else last_pos.ayah_number + 1
    else:
        initial_surah = None
        initial_ayah = None

    page_regions = []
    for pos in page_qs:
        for region in _regions_from_position(pos):
            page_regions.append({
                **region,
                "surah_number": pos.surah_number,
                "ayah_number": pos.ayah_number,
                "mushaf_key": pos.mushaf_key,
            })

    return render(request, "quran_studio/ayah_editor.html", {
        "page_number": page_number,
        "mushaf": mushaf,
        "mushafs": MUSHAFS,
        "current_mushaf": current_mushaf,
        "initial_surah": initial_surah,
        "initial_ayah": initial_ayah,
        "page_regions_json": json.dumps(page_regions, ensure_ascii=False),
        "mushaf_dimensions": get_all_mushaf_dimensions(),
    })


def _compute_bbox_from_regions(regions):
    xs, ys, x2s, y2s = [], [], [], []

    for r in regions:
        x = r["x"]
        y = r["y"]
        w = r["width"]
        h = r["height"]

        xs.append(x)
        ys.append(y)
        x2s.append(x + w)
        y2s.append(y + h)

    if not xs:
        raise ValueError("No valid regions for bbox")

    min_x = min(xs)
    min_y = min(ys)
    max_x2 = max(x2s)
    max_y2 = max(y2s)

    width = max_x2 - min_x
    height = max_y2 - min_y

    return (
        float(f"{min_x:.4f}"),
        float(f"{min_y:.4f}"),
        float(f"{width:.4f}"),
        float(f"{height:.4f}"),
    )


def _update_csv_row(mushaf_key, surah_number, ayah_number, page_number, x, y, width, height, regions):
    header = [
        "mushaf_key",
        "surah_number",
        "ayah_number",
        "page_number",
        "x",
        "y",
        "width",
        "height",
        "polygon",
    ]

    rows = []
    if CSV_PATH.exists():
        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for row in reader:
                    if not row:
                        continue
                    rows.append({key: row.get(key, "") for key in header})

    polygon_str = json.dumps(regions, ensure_ascii=False)
    new_row = {
        "mushaf_key": mushaf_key,
        "surah_number": str(surah_number),
        "ayah_number": "" if ayah_number is None else str(ayah_number),
        "page_number": str(page_number),
        "x": f"{x}",
        "y": f"{y}",
        "width": f"{width}",
        "height": f"{height}",
        "polygon": polygon_str,
    }

    updated = False
    for idx, row in enumerate(rows):
        if (
            row.get("mushaf_key") == mushaf_key
            and row.get("surah_number") == str(surah_number)
            and row.get("ayah_number") == new_row["ayah_number"]
            and row.get("page_number") == str(page_number)
        ):
            rows[idx] = new_row
            updated = True
            break

    if not updated:
        rows.append(new_row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


@login_required
@permission_required(STUDIO_PERMISSION)
def save_ayah_position(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "POST only"},
            status=405,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON"},
            status=400,
        )

    try:
        mushaf_key = _clean_mushaf_key(payload.get("mushaf_key"))
        surah_number = int(payload.get("surah_number"))

        ayah_raw = payload.get("ayah_number")
        if ayah_raw in (None, "", "null"):
            ayah_number = None
        else:
            ayah_number = int(ayah_raw)

        page_number = int(payload.get("page_number"))
        regions = _normalize_regions(payload.get("regions") or [])
    except (TypeError, ValueError) as e:
        return JsonResponse(
            {"status": "error", "message": f"Bad fields: {e}"},
            status=400,
        )

    if surah_number <= 0 or surah_number > MAX_SURAH_NUMBER:
        return JsonResponse(
            {"status": "error", "message": "Invalid surah number"},
            status=400,
        )

    if ayah_number is not None and ayah_number < 0:
        return JsonResponse(
            {"status": "error", "message": "Invalid ayah number"},
            status=400,
        )

    if page_number <= 0 or page_number > MAX_PAGE_NUMBER:
        return JsonResponse(
            {"status": "error", "message": "Invalid page number"},
            status=400,
        )

    try:
        x, y, width, height = _compute_bbox_from_regions(regions)
    except ValueError as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=400,
        )

    obj, created = AyahPosition.objects.update_or_create(
        mushaf_key=mushaf_key,
        surah_number=surah_number,
        ayah_number=ayah_number,
        page_number=page_number,
        defaults={
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "polygon": regions,
        },
    )

    _update_csv_row(
        mushaf_key=mushaf_key,
        surah_number=surah_number,
        ayah_number=ayah_number,
        page_number=page_number,
        x=x,
        y=y,
        width=width,
        height=height,
        regions=regions,
    )

    return JsonResponse({
        "status": "ok",
        "created": created,
        "id": obj.id,
        "mushaf_key": obj.mushaf_key,
    })


@login_required
@permission_required(STUDIO_PERMISSION)
def get_ayah_position(request):
    if request.method != "GET":
        return JsonResponse(
            {"status": "error", "message": "GET only"},
            status=405,
        )

    try:
        mushaf_key = _clean_mushaf_key(request.GET.get("mushaf_key") or request.GET.get("mushaf"))
        surah_number = int(request.GET.get("surah_number", "0"))
        ayah_number = int(request.GET.get("ayah_number", "0"))
        page_number = int(request.GET.get("page_number", "0"))
    except ValueError:
        return JsonResponse(
            {"status": "error", "message": "Bad parameters"},
            status=400,
        )

    if surah_number <= 0 or surah_number > MAX_SURAH_NUMBER:
        return JsonResponse(
            {"status": "error", "message": "Invalid surah number"},
            status=400,
        )

    if ayah_number < 0:
        return JsonResponse(
            {"status": "error", "message": "Invalid ayah number"},
            status=400,
        )

    if page_number <= 0 or page_number > MAX_PAGE_NUMBER:
        return JsonResponse(
            {"status": "error", "message": "Invalid page number"},
            status=400,
        )

    try:
        pos = AyahPosition.objects.get(
            mushaf_key=mushaf_key,
            surah_number=surah_number,
            ayah_number=ayah_number,
            page_number=page_number,
        )
    except AyahPosition.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Not found"},
            status=404,
        )

    return JsonResponse({
        "status": "ok",
        "mushaf_key": pos.mushaf_key,
        "surah_number": pos.surah_number,
        "ayah_number": pos.ayah_number,
        "page_number": pos.page_number,
        "regions": _regions_from_position(pos),
        "bbox": {
            "x": pos.x,
            "y": pos.y,
            "width": pos.width,
            "height": pos.height,
        },
    })


def _save_qari_image(image_file, code):
    if not image_file or not code:
        return ""

    upload_dir = Path(settings.MEDIA_ROOT) / "images" / "qurra"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(image_file.name).suffix.lower() or ".jpg"
    filename = f"{code}{ext}"
    file_path = upload_dir / filename

    if file_path.exists():
        file_path.unlink()

    with open(file_path, "wb+") as destination:
        for chunk in image_file.chunks():
            destination.write(chunk)

    return filename


def _delete_qari_image(filename):
    if not filename:
        return

    file_path = Path(settings.BASE_DIR) / "static" / "images" / "qurra" / filename
    if file_path.exists() and file_path.is_file():
        os.remove(file_path)


@login_required
@permission_required(STUDIO_PERMISSION)
def qurra_list(request):
    if request.method == "POST":
        qari_id = request.POST.get("qari_id")

        code = (request.POST.get("code") or "").strip()
        name_ar = (request.POST.get("name_ar") or "").strip()
        name_en = (request.POST.get("name_en") or "").strip()
        image_file = request.FILES.get("image")

        if not code or not name_ar:
            messages.error(request, "الكود والاسم العربي مطلوبان.")
            return redirect("quran_studio:qurra_list")

        if qari_id:
            qari = get_object_or_404(Qurra, pk=qari_id)

            old_code = qari.code
            old_image = qari.image

            qari.code = code
            qari.name_ar = name_ar
            qari.name_en = name_en

            if image_file:
                new_image = _save_qari_image(image_file, code)
                qari.image = new_image
                if old_image and old_image != new_image:
                    _delete_qari_image(old_image)
            else:
                if old_image and old_code != code:
                    old_ext = Path(old_image).suffix.lower()
                    new_image_name = f"{code}{old_ext}"

                    old_path = Path(settings.BASE_DIR) / "static" / "images" / "qurra" / old_image
                    new_path = Path(settings.BASE_DIR) / "static" / "images" / "qurra" / new_image_name

                    if old_path.exists() and old_path.is_file():
                        if new_path.exists():
                            new_path.unlink()
                        old_path.rename(new_path)
                        qari.image = new_image_name

            qari.save()
            messages.success(request, "تم تعديل بيانات القارئ بنجاح.")
        else:
            image_name = _save_qari_image(image_file, code) if image_file else ""

            Qurra.objects.create(
                code=code,
                name_ar=name_ar,
                name_en=name_en,
                image=image_name,
            )
            messages.success(request, "تمت إضافة القارئ بنجاح.")

        return redirect("quran_studio:qurra_list")

    edit_id = request.GET.get("edit")
    edit_qari = None
    if edit_id:
        edit_qari = get_object_or_404(Qurra, pk=edit_id)

    qurra = Qurra.objects.all().order_by("pk")

    return render(request, "quran_studio/qurra.html", {
        "qurra": qurra,
        "edit_qari": edit_qari,
    })


@login_required
@permission_required(STUDIO_PERMISSION)
def qari_toggle_visibility(request, pk):
    if request.method != "POST":
        return redirect("quran_studio:qurra_list")

    qari = get_object_or_404(Qurra, pk=pk)
    qari.is_visible = not qari.is_visible
    qari.save(update_fields=["is_visible"])

    return JsonResponse({"ok": True, "is_visible": qari.is_visible})


@login_required
@permission_required(STUDIO_PERMISSION)
def qari_delete(request, pk):
    if request.method != "POST":
        return redirect("quran_studio:qurra_list")

    qari = get_object_or_404(Qurra, pk=pk)

    if qari.image:
        _delete_qari_image(qari.image)

    qari.delete()
    messages.success(request, "تم حذف القارئ بنجاح.")

    return redirect("quran_studio:qurra_list")