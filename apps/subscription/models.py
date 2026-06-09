from uuid import uuid4

from decimal import Decimal

from django.conf import settings
from django.db import models


class SubscriptionPlan(models.Model):
    title = models.CharField(max_length=255, verbose_name="اسم الباقة")
    duration_months = models.PositiveSmallIntegerField(verbose_name="المدة بالأشهر")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="المبلغ",
    )
    minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="دقائق الباقة",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="وصف الباقة",
    )
    is_active = models.BooleanField(default=True, verbose_name="مفعّلة")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "باقة اشتراك"
        verbose_name_plural = "باقات الاشتراك"

    def __str__(self):
        return self.title


class StudentSubscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        EXPIRED = "expired", "منتهي"
        CANCELLED = "cancelled", "ملغي"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PAID = "paid", "مدفوع"
        FAILED = "failed", "فشل"

    class DisplayStatus:
        ACTIVE = "active"
        EXPIRED = "expired"
        CANCELLED = "cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_subscriptions",
        verbose_name="المستخدم",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="student_subscriptions",
        verbose_name="الباقة",
    )
    plan_title = models.CharField(max_length=255, verbose_name="اسم الباقة")
    duration_months = models.PositiveIntegerField(verbose_name="مدة الاشتراك بالأشهر")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name="حالة الدفع",
    )
    payment_method = models.CharField(max_length=64, blank=True, default="")
    transaction_reference = models.CharField(max_length=128, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    plan_minutes_added = models.PositiveIntegerField(
        default=0,
        verbose_name="دقائق مضافة",
    )
    minutes_before = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="الدقائق قبل العملية",
    )
    minutes_after = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="الدقائق بعد العملية",
    )
    expiry_before = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الانتهاء قبل العملية",
    )
    expiry_after = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الانتهاء بعد العملية",
    )
    transaction_type = models.CharField(
        max_length=32,
        blank=True,
        default="purchase",
        verbose_name="نوع العملية",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "اشتراك طالب"
        verbose_name_plural = "سجل اشتراكات الطلاب"

    def __str__(self):
        return f"{self.user_id} — {self.plan_title}"


class StudentSubscriptionBalance(models.Model):
    """One current subscription summary per student."""

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        EXPIRED = "expired", "منتهي"
        CANCELLED = "cancelled", "ملغي"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription_balance",
        verbose_name="المستخدم",
    )
    current_plan_title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="الباقة الحالية",
    )
    remaining_minutes = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="الدقائق المتبقية",
    )
    used_minutes = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="الدقائق المستخدمة",
    )
    expires_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الانتهاء",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EXPIRED,
        verbose_name="الحالة",
    )
    last_purchase_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخر عملية شراء",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "رصيد اشتراك طالب"
        verbose_name_plural = "أرصدة اشتراك الطلاب"

    def __str__(self):
        return f"{self.user_id} — {self.remaining_minutes} دقيقة"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_confirmed = models.BooleanField(default=True, verbose_name="تم التأكيد")
    unsubscribe_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    subscribed_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الاشتراك")
    unsubscribed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ إلغاء الاشتراك")

    class Meta:
        ordering = ["-subscribed_at"]
        verbose_name = "مشترك نشرة بريدية"
        verbose_name_plural = "مشتركو النشرة البريدية"

    def __str__(self):
        return self.email