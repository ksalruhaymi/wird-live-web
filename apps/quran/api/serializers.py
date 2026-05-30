from rest_framework import serializers
from apps.quran.models import (
    Surah,
    Ayah,
    AyahPosition,
    TafsirBook,
    Tafsir,
    Qurra,
)


class SurahSerializer(serializers.ModelSerializer):
    class Meta:
        model = Surah
        fields = [
            "surah_number",
            "surah_name_ar",
            "surah_name_en",
            "page_start",
            "page_end",
            "ayah_count",
            "revelation_type",
        ]


class AyahSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ayah
        fields = [
            "id",
            "surah_number",
            "ayah_number",
            "page_number",
            "juz_number",
            "text",
        ]


class AyahPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AyahPosition
        fields = [
            "id",
            "surah_number",
            "ayah_number",
            "page_number",
            "x",
            "y",
            "width",
            "height",
            "polygon",
        ]


class TafsirBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = TafsirBook
        fields = [
            "id",
            "number",
            "name",
            "lang",
            "api",
            "image",
            "author",
            "info",
            "is_active",
            "sort_order",
        ]


class TafsirSerializer(serializers.ModelSerializer):
    book = TafsirBookSerializer(read_only=True)

    class Meta:
        model = Tafsir
        fields = [
            "id",
            "book",
            "surah_id",
            "ayah_number",
            "text",
        ]


class QurraSerializer(serializers.ModelSerializer):
    """عقد القارئ كما يستهلكه عميل Flutter (QariModel).

    يضيف حقولاً افتراضية للعميل (number, fullname, info, supported_mushafs)
    حتى لو لم تكن مخزنة على نموذج Qurra مباشرةً، حفاظاً على توافق الـ API.
    """

    number = serializers.SerializerMethodField()
    fullname = serializers.SerializerMethodField()
    info = serializers.SerializerMethodField()
    supported_mushafs = serializers.SerializerMethodField()

    class Meta:
        model = Qurra
        fields = [
            "id",
            "number",
            "name_ar",
            "name_en",
            "code",
            "fullname",
            "info",
            "image",
            "supported_mushafs",
        ]

    def get_number(self, obj) -> int:
        return obj.id

    def get_fullname(self, obj) -> str:
        return obj.name_ar or obj.name_en or obj.code

    def get_info(self, obj) -> str:
        return ""

    def get_supported_mushafs(self, obj) -> list:
        # يُحسب من الـ view لأن الفحص يعتمد على نظام الملفات (MEDIA_ROOT)
        ctx = self.context.get("supported_mushafs_for_code") if self.context else None
        if callable(ctx):
            return ctx(obj.code) or []
        return []


class MetaConfigSerializer(serializers.Serializer):
    # This is not a DB model, just a response schema
    default_mushaf = serializers.CharField()
    total_pages = serializers.IntegerField()
    notes = serializers.CharField()