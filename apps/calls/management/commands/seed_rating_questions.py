from django.core.management.base import BaseCommand
from django.db import transaction

from apps.calls.models import RatingCategoryConfig, RatingQuestion

DEFAULT_QUESTIONS = [
    (
        RatingQuestion.Category.TEACHER,
        [
            ("هل المعلّم متمكن؟", 1),
            ("هل المعلّم واضح وسهل؟", 2),
            ("ما رأيك في جودة الصوت؟", 3),
        ],
    ),
    (
        RatingQuestion.Category.STUDENT,
        [
            ("هل الطالب متمكن؟", 1),
            ("هل الطالب سهل وواضح؟", 2),
            ("ما رأيك في جودة الصوت؟", 3),
        ],
    ),
    (
        RatingQuestion.Category.DEMO_TEACHER,
        [
            ("ما رأيك في الجلسة التجريبية؟", 1),
            ("هل الصوت كان واضحًا؟", 2),
        ],
    ),
]


class Command(BaseCommand):
    help = "Seed default rating questions for teacher, student, and demo teacher."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0

        for category, questions in DEFAULT_QUESTIONS:
            RatingCategoryConfig.objects.update_or_create(
                category=category,
                defaults={"is_active": True},
            )
            for text, order in questions:
                obj, was_created = RatingQuestion.objects.update_or_create(
                    category=category,
                    order=order,
                    defaults={
                        "question_text": text,
                        "is_active": True,
                        "max_stars": 5,
                    },
                )
                if obj.question_text != text:
                    obj.question_text = text
                    obj.is_active = True
                    obj.max_stars = 5
                    obj.save()
                    updated += 1
                elif was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Rating questions seeded (created={created}, updated={updated})."
            )
        )
