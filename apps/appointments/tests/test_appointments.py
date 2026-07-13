from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    ExceptionType,
    RecurrenceType,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.booking import book_slot
from apps.appointments.services.call_link import process_due_reminders, start_appointment_call
from apps.appointments.services.cancellation import (
    cancel_by_student,
    cancel_by_teacher,
    mark_appointment_status,
)
from apps.appointments.services.queries import student_appointments, upcoming_count_for_student
from apps.appointments.services.rules import add_availability_exception, create_availability_rule
from apps.appointments.services.settings_service import (
    get_or_create_booking_settings,
    update_booking_settings,
)
from apps.appointments.services.slot_generation import generate_slots_for_teacher
from apps.calls.models import CallSession
from apps.subscription.models import SubscriptionPlan
from apps.subscription.services import create_student_subscription
from apps.tutoring.models import TeacherProfile as TutoringTeacherProfile
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER
from identity.rbac.models import Role

User = get_user_model()
RIYADH = ZoneInfo("Asia/Riyadh")

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


def _make_teacher(username: str):
    teacher = User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_TEACHER,
        full_name=f"Teacher {username}",
    )
    TutoringTeacherProfile.objects.create(
        user=teacher,
        display_name=f"المعلم {username}",
        approval_status=TutoringTeacherProfile.ApprovalStatus.APPROVED,
        is_approved=True,
        can_audio=True,
        can_video=True,
    )
    return teacher


def _make_student_with_balance(username: str):
    student = User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_STUDENT,
        full_name=f"Student {username}",
    )
    plan = SubscriptionPlan.objects.create(
        title=f"plan-{username}",
        duration_months=1,
        price=Decimal("50.00"),
        minutes=120,
        is_active=True,
    )
    create_student_subscription(student, plan_id=plan.id)
    return student


def _aware(day, hour: int, minute: int = 0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), RIYADH)


def _create_slot(teacher, start_at, end_at, *, status=SlotStatus.AVAILABLE, source_rule=None):
    return AppointmentSlot.objects.create(
        teacher=teacher,
        source_rule=source_rule,
        start_at=start_at,
        end_at=end_at,
        status=status,
    )


def _rule_day_ahead(days: int = 2):
    return timezone.localdate() + timedelta(days=days)


@override_settings(AXES_ENABLED=False)
class AppointmentBookingSuccessTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_book_ok_t")
        self.student = _make_student_with_balance("appt_book_ok_s")
        start = _rule_day_ahead(2)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "10:00",
                "end_time": "12:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slot = (
            AppointmentSlot.objects.filter(teacher=self.teacher, status=SlotStatus.AVAILABLE)
            .order_by("start_at")
            .first()
        )

    def test_successful_book(self):
        appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
            student_notes="تسميع",
        )
        self.assertEqual(appt.status, AppointmentStatus.CONFIRMED)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, SlotStatus.RESERVED)


@override_settings(AXES_ENABLED=False)
class AppointmentBookingConflictTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_book_conflict_t")
        self.student = _make_student_with_balance("appt_book_conflict_s")
        self.student2 = _make_student_with_balance("appt_book_conflict_s2")
        start = _rule_day_ahead(2)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slot = AppointmentSlot.objects.filter(teacher=self.teacher).order_by("start_at").first()

    def test_book_already_reserved_slot_unavailable(self):
        book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student2,
                slot_id=self.slot.id,
                session_type=SessionType.NEAR_REVISION,
            )
        self.assertEqual(ctx.exception.code, "slot_unavailable")

    def test_book_past_slot_rejected(self):
        past_start = timezone.now() - timedelta(hours=3)
        past_slot = _create_slot(
            self.teacher,
            past_start,
            past_start + timedelta(minutes=30),
        )
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student,
                slot_id=past_slot.id,
                session_type=SessionType.RECITATION,
            )
        self.assertEqual(ctx.exception.code, "slot_in_past")

    def test_booking_disabled_blocks(self):
        update_booking_settings(self.teacher, booking_enabled=False)
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student,
                slot_id=self.slot.id,
                session_type=SessionType.RECITATION,
            )
        self.assertEqual(ctx.exception.code, "booking_disabled")

    def test_student_overlapping_appointments(self):
        day = _rule_day_ahead(5)
        slot_a = _create_slot(self.teacher, _aware(day, 15, 0), _aware(day, 15, 30))
        slot_b = _create_slot(self.teacher, _aware(day, 15, 15), _aware(day, 15, 45))
        book_slot(
            student=self.student,
            slot_id=slot_a.id,
            session_type=SessionType.RECITATION,
        )
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student,
                slot_id=slot_b.id,
                session_type=SessionType.NEW_MEMORIZATION,
            )
        self.assertEqual(ctx.exception.code, "student_overlap")

    def test_other_session_type_requires_description(self):
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student,
                slot_id=self.slot.id,
                session_type=SessionType.OTHER,
            )
        self.assertEqual(ctx.exception.code, "other_required")

        appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.OTHER,
            session_type_other="جلسة خاصة",
        )
        self.assertEqual(appt.session_type_other, "جلسة خاصة")

    def test_student_notes_too_long(self):
        with self.assertRaises(AppointmentError) as ctx:
            book_slot(
                student=self.student,
                slot_id=self.slot.id,
                session_type=SessionType.RECITATION,
                student_notes="ن" * 501,
            )
        self.assertEqual(ctx.exception.code, "notes_too_long")


@override_settings(AXES_ENABLED=False)
class AppointmentRaceTests(TransactionTestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_race_teacher")
        self.student_a = _make_student_with_balance("appt_race_a")
        self.student_b = _make_student_with_balance("appt_race_b")
        start = _rule_day_ahead(4)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "11:00",
                "end_time": "11:30",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slot = AppointmentSlot.objects.filter(teacher=self.teacher).first()

    def test_sequential_race_one_wins(self):
        errors = []
        successes = []

        def attempt(student):
            try:
                appt = book_slot(
                    student=student,
                    slot_id=self.slot.id,
                    session_type=SessionType.RECITATION,
                )
                successes.append(appt.id)
            except AppointmentError as exc:
                errors.append(exc.code)

        attempt(self.student_a)
        attempt(self.student_b)
        self.assertEqual(len(successes), 1)
        self.assertEqual(Appointment.objects.filter(slot=self.slot).count(), 1)
        self.assertTrue(errors == [] or errors == ["slot_unavailable"])


@override_settings(AXES_ENABLED=False)
class AvailabilityRuleValidationTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_rule_val_t")

    def test_teacher_overlapping_window_on_create(self):
        start = _rule_day_ahead(3)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        with self.assertRaises(AppointmentError) as ctx:
            create_availability_rule(
                self.teacher,
                {
                    "start_date": start.isoformat(),
                    "start_time": "09:30",
                    "end_time": "10:30",
                    "slot_duration_minutes": 30,
                    "break_minutes": 0,
                    "recurrence_type": RecurrenceType.NONE,
                },
            )
        self.assertEqual(ctx.exception.code, "teacher_overlap")

    def test_end_time_before_start_time_invalid_window(self):
        start = _rule_day_ahead(3)
        with self.assertRaises(AppointmentError) as ctx:
            create_availability_rule(
                self.teacher,
                {
                    "start_date": start.isoformat(),
                    "start_time": "12:00",
                    "end_time": "11:00",
                    "slot_duration_minutes": 30,
                    "break_minutes": 0,
                    "recurrence_type": RecurrenceType.NONE,
                },
            )
        self.assertEqual(ctx.exception.code, "invalid_window")


@override_settings(AXES_ENABLED=False)
class AppointmentCancellationTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_cancel_t")
        self.other_teacher = _make_teacher("appt_cancel_other_t")
        self.student = _make_student_with_balance("appt_cancel_s")
        start = _rule_day_ahead(3)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "13:00",
                "end_time": "15:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slots = list(
            AppointmentSlot.objects.filter(teacher=self.teacher).order_by("start_at")
        )

    def test_student_cancel_within_deadline_reopens_slot(self):
        slot = self.slots[0]
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        cancel_by_student(appt.id, self.student, reason="ظروف")
        appt.refresh_from_db()
        slot.refresh_from_db()
        self.assertEqual(appt.status, AppointmentStatus.CANCELLED_BY_STUDENT)
        self.assertEqual(slot.status, SlotStatus.AVAILABLE)

    def test_student_cancel_after_deadline(self):
        slot = self.slots[0]
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        update_booking_settings(self.teacher, cancellation_deadline_minutes=100_000)
        with self.assertRaises(AppointmentError) as ctx:
            cancel_by_student(appt.id, self.student, reason="متأخر")
        self.assertEqual(ctx.exception.code, "cancel_deadline")

    def test_teacher_cancel_reopen_slot_true(self):
        slot = self.slots[0]
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        cancel_by_teacher(appt.id, self.teacher, reason="سفر", reopen_slot=True)
        slot.refresh_from_db()
        self.assertEqual(slot.status, SlotStatus.AVAILABLE)

    def test_teacher_cancel_reopen_slot_false(self):
        slot = self.slots[1]
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        cancel_by_teacher(appt.id, self.teacher, reason="إغلاق", reopen_slot=False)
        slot.refresh_from_db()
        self.assertEqual(slot.status, SlotStatus.CANCELLED)

    def test_teacher_cannot_cancel_another_teachers_booking(self):
        slot = self.slots[0]
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        with self.assertRaises(AppointmentError) as ctx:
            cancel_by_teacher(appt.id, self.other_teacher, reason="لا")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.status, 404)


@override_settings(AXES_ENABLED=False)
class AppointmentCallWindowTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_call_t")
        self.student = _make_student_with_balance("appt_call_s")
        day = _rule_day_ahead(2)
        self.slot = _create_slot(self.teacher, _aware(day, 16, 0), _aware(day, 16, 30))
        self.appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )

    def _mock_call(self):
        return CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.MOCK,
            status=CallSession.Status.ACTIVE,
            channel_name="test-channel",
        )

    def test_start_outside_window_before(self):
        fake_now = self.slot.start_at - timedelta(minutes=20)
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with patch(
                "apps.appointments.services.call_link.create_scheduled_call_session"
            ) as mock_create:
                with self.assertRaises(AppointmentError) as ctx:
                    start_appointment_call(self.student, self.appt.id)
        self.assertEqual(ctx.exception.code, "outside_call_window")
        mock_create.assert_not_called()

    def test_start_inside_window(self):
        fake_now = self.slot.start_at - timedelta(minutes=5)
        call = self._mock_call()
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with patch(
                "apps.appointments.services.call_link.create_scheduled_call_session",
                return_value=call,
            ):
                appt, started = start_appointment_call(self.student, self.appt.id)
        self.assertEqual(started.id, call.id)
        appt.refresh_from_db()
        self.assertEqual(appt.status, AppointmentStatus.IN_PROGRESS)
        self.assertEqual(appt.call_session_id, call.id)

    def test_start_outside_window_after(self):
        fake_now = self.slot.start_at + timedelta(minutes=15)
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with patch(
                "apps.appointments.services.call_link.create_scheduled_call_session"
            ) as mock_create:
                with self.assertRaises(AppointmentError) as ctx:
                    start_appointment_call(self.student, self.appt.id)
        self.assertEqual(ctx.exception.code, "outside_call_window")
        mock_create.assert_not_called()

    def test_second_start_returns_same_call_session(self):
        fake_now = self.slot.start_at - timedelta(minutes=5)
        call = self._mock_call()
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with patch(
                "apps.appointments.services.call_link.create_scheduled_call_session",
                return_value=call,
            ) as mock_create:
                _, first = start_appointment_call(self.student, self.appt.id)
                _, second = start_appointment_call(self.student, self.appt.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(mock_create.call_count, 1)

    def test_cancelled_appointment_cannot_start_call(self):
        cancel_by_student(self.appt.id, self.student, reason="إلغاء")
        fake_now = self.slot.start_at - timedelta(minutes=5)
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with self.assertRaises(AppointmentError) as ctx:
                start_appointment_call(self.student, self.appt.id)
        self.assertEqual(ctx.exception.code, "outside_call_window")

    def test_completed_appointment_cannot_start_call(self):
        mark_appointment_status(
            self.appt.id,
            self.teacher,
            new_status=AppointmentStatus.COMPLETED,
        )
        fake_now = self.slot.start_at - timedelta(minutes=5)
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with self.assertRaises(AppointmentError) as ctx:
                start_appointment_call(self.student, self.appt.id)
        self.assertEqual(ctx.exception.code, "outside_call_window")


@override_settings(AXES_ENABLED=False)
class AppointmentSlotGenerationTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_slots_t")

    def test_weekly_recurrence_generates_multiple_weeks(self):
        start = _rule_day_ahead(1)
        end = start + timedelta(days=21)
        rule = create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "start_time": "14:00",
                "end_time": "14:30",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.WEEKLY,
            },
        )
        slots = list(
            AppointmentSlot.objects.filter(teacher=self.teacher, source_rule=rule).order_by(
                "start_at"
            )
        )
        self.assertGreaterEqual(len(slots), 3)
        weekdays = {timezone.localtime(s.start_at).date().isoweekday() for s in slots}
        self.assertEqual(weekdays, {start.isoweekday()})

    def test_idempotent_generate_slots_for_teacher(self):
        start = _rule_day_ahead(1)
        rule = create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "16:00",
                "end_time": "18:00",
                "slot_duration_minutes": 30,
                "break_minutes": 5,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        first_count = AppointmentSlot.objects.filter(
            teacher=self.teacher, source_rule=rule
        ).count()
        generate_slots_for_teacher(self.teacher)
        second_count = AppointmentSlot.objects.filter(
            teacher=self.teacher, source_rule=rule
        ).count()
        self.assertEqual(first_count, second_count)

    def test_break_between_sessions(self):
        start = _rule_day_ahead(1)
        rule = create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "16:00",
                "end_time": "18:00",
                "slot_duration_minutes": 30,
                "break_minutes": 5,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        slots = list(
            AppointmentSlot.objects.filter(teacher=self.teacher, source_rule=rule).order_by(
                "start_at"
            )
        )
        self.assertEqual(len(slots), 3)
        self.assertEqual(timezone.localtime(slots[0].start_at).strftime("%H:%M"), "16:00")
        self.assertEqual(timezone.localtime(slots[0].end_at).strftime("%H:%M"), "16:30")
        self.assertEqual(timezone.localtime(slots[1].start_at).strftime("%H:%M"), "16:35")

    def test_no_partial_slot_at_end(self):
        start = _rule_day_ahead(1)
        rule = create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "16:00",
                "end_time": "18:00",
                "slot_duration_minutes": 30,
                "break_minutes": 5,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        slots = list(
            AppointmentSlot.objects.filter(teacher=self.teacher, source_rule=rule).order_by(
                "start_at"
            )
        )
        # 16:00-16:30, 16:35-17:05, 17:10-17:40 — not 17:45-18:15
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(s.end_at <= _aware(start, 18, 0) for s in slots))

    def test_closed_day_exception_blocks_slots(self):
        start = _rule_day_ahead(2)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.assertTrue(
            AppointmentSlot.objects.filter(
                teacher=self.teacher, start_at__date=start, status=SlotStatus.AVAILABLE
            ).exists()
        )
        add_availability_exception(
            self.teacher,
            {
                "date": start.isoformat(),
                "exception_type": ExceptionType.CLOSED_DAY,
                "reason": "إجازة",
            },
        )
        self.assertFalse(
            AppointmentSlot.objects.filter(
                teacher=self.teacher, start_at__date=start, status=SlotStatus.AVAILABLE
            ).exists()
        )
        self.assertTrue(
            AppointmentSlot.objects.filter(
                teacher=self.teacher, start_at__date=start, status=SlotStatus.BLOCKED
            ).exists()
        )

    def test_closed_range_exception(self):
        start = _rule_day_ahead(2)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        add_availability_exception(
            self.teacher,
            {
                "date": start.isoformat(),
                "exception_type": ExceptionType.CLOSED_RANGE,
                "start_time": "09:00",
                "end_time": "10:00",
                "reason": "اجتماع",
            },
        )
        blocked = AppointmentSlot.objects.filter(
            teacher=self.teacher,
            start_at__date=start,
            status=SlotStatus.BLOCKED,
        )
        available = AppointmentSlot.objects.filter(
            teacher=self.teacher,
            start_at__date=start,
            status=SlotStatus.AVAILABLE,
        )
        self.assertTrue(blocked.exists())
        self.assertTrue(available.exists())
        for slot in blocked:
            self.assertTrue(slot.start_at < _aware(start, 10, 0))

    def test_add_slots_exception_creates_slots(self):
        get_or_create_booking_settings(self.teacher)
        day = _rule_day_ahead(3)
        before = AppointmentSlot.objects.filter(teacher=self.teacher).count()
        add_availability_exception(
            self.teacher,
            {
                "date": day.isoformat(),
                "exception_type": ExceptionType.ADD_SLOTS,
                "start_time": "20:00",
                "end_time": "21:00",
                "reason": "وقت إضافي",
            },
        )
        after = AppointmentSlot.objects.filter(teacher=self.teacher).count()
        self.assertGreater(after, before)
        self.assertTrue(
            AppointmentSlot.objects.filter(
                teacher=self.teacher,
                start_at__date=day,
                status=SlotStatus.AVAILABLE,
            ).exists()
        )

    def test_generate_twice_for_90_day_window_no_duplicates(self):
        start = _rule_day_ahead(1)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=60)).isoformat(),
                "start_time": "08:00",
                "end_time": "08:30",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.WEEKLY,
            },
        )
        generate_slots_for_teacher(self.teacher, window_days=90)
        count_1 = AppointmentSlot.objects.filter(teacher=self.teacher).count()
        generate_slots_for_teacher(self.teacher, window_days=90)
        count_2 = AppointmentSlot.objects.filter(teacher=self.teacher).count()
        self.assertEqual(count_1, count_2)


@override_settings(AXES_ENABLED=False)
class AppointmentReminderTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_remind_t")
        self.student = _make_student_with_balance("appt_remind_s")
        day = _rule_day_ahead(2)
        self.slot = _create_slot(self.teacher, _aware(day, 18, 0), _aware(day, 18, 30))
        self.appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )

    def test_process_due_reminders_sends_once(self):
        # 1h window: start between now+50m and now+60m
        fake_now = self.slot.start_at - timedelta(minutes=55)
        with patch(
            "apps.appointments.services.call_link.notify_appointment_reminder"
        ) as mock_notify:
            with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
                first = process_due_reminders(now=fake_now)
                second = process_due_reminders(now=fake_now)
        self.assertEqual(first["1h"], 1)
        self.assertEqual(second["1h"], 0)
        self.assertEqual(mock_notify.call_count, 1)
        self.appt.refresh_from_db()
        self.assertIsNotNone(self.appt.reminder_1h_sent_at)

    def test_process_due_reminders_skips_cancelled(self):
        cancel_by_student(self.appt.id, self.student, reason="إلغاء")
        fake_now = self.slot.start_at - timedelta(minutes=55)
        with patch(
            "apps.appointments.services.call_link.notify_appointment_reminder"
        ) as mock_notify:
            sent = process_due_reminders(now=fake_now)
        self.assertEqual(sent["1h"], 0)
        mock_notify.assert_not_called()


@override_settings(AXES_ENABLED=False)
class AppointmentQueryBucketTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_bucket_t")
        self.student = _make_student_with_balance("appt_bucket_s")
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        past_day = today - timedelta(days=1)

        # Today (may be in the past relative to now — create appointment directly)
        today_slot = _create_slot(
            self.teacher,
            _aware(today, 23, 0),
            _aware(today, 23, 30),
        )
        self.today_appt = Appointment.objects.create(
            teacher=self.teacher,
            student=self.student,
            slot=today_slot,
            session_type=SessionType.RECITATION,
            status=AppointmentStatus.CONFIRMED,
            booked_at=timezone.now(),
            confirmed_at=timezone.now(),
        )
        today_slot.status = SlotStatus.RESERVED
        today_slot.save(update_fields=["status", "updated_at"])

        upcoming_slot = _create_slot(
            self.teacher,
            _aware(tomorrow + timedelta(days=1), 10, 0),
            _aware(tomorrow + timedelta(days=1), 10, 30),
        )
        self.upcoming_appt = book_slot(
            student=self.student,
            slot_id=upcoming_slot.id,
            session_type=SessionType.RECITATION,
        )

        past_slot = _create_slot(
            self.teacher,
            _aware(past_day, 10, 0),
            _aware(past_day, 10, 30),
            status=SlotStatus.RESERVED,
        )
        self.past_appt = Appointment.objects.create(
            teacher=self.teacher,
            student=self.student,
            slot=past_slot,
            session_type=SessionType.RECITATION,
            status=AppointmentStatus.COMPLETED,
            booked_at=timezone.now() - timedelta(days=2),
            confirmed_at=timezone.now() - timedelta(days=2),
            completed_at=timezone.now() - timedelta(days=1),
        )

        cancel_slot = _create_slot(
            self.teacher,
            _aware(tomorrow + timedelta(days=2), 11, 0),
            _aware(tomorrow + timedelta(days=2), 11, 30),
        )
        self.cancelled_appt = book_slot(
            student=self.student,
            slot_id=cancel_slot.id,
            session_type=SessionType.NEAR_REVISION,
        )
        cancel_by_student(self.cancelled_appt.id, self.student, reason="إلغاء")

    def test_student_appointments_buckets(self):
        today_ids = set(student_appointments(self.student, bucket="today").values_list("id", flat=True))
        upcoming_ids = set(
            student_appointments(self.student, bucket="upcoming").values_list("id", flat=True)
        )
        past_ids = set(student_appointments(self.student, bucket="past").values_list("id", flat=True))
        cancelled_ids = set(
            student_appointments(self.student, bucket="cancelled").values_list("id", flat=True)
        )

        self.assertIn(self.today_appt.id, today_ids)
        self.assertIn(self.upcoming_appt.id, upcoming_ids)
        self.assertIn(self.past_appt.id, past_ids)
        self.assertIn(self.cancelled_appt.id, cancelled_ids)
        self.assertNotIn(self.cancelled_appt.id, upcoming_ids)


@override_settings(AXES_ENABLED=False)
class AppointmentStatusMarkTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_mark_t")
        self.student = _make_student_with_balance("appt_mark_s")
        day = _rule_day_ahead(2)
        self.slot = _create_slot(self.teacher, _aware(day, 12, 0), _aware(day, 12, 30))
        self.appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )

    def test_mark_allowed_completed_and_no_show(self):
        completed = mark_appointment_status(
            self.appt.id,
            self.teacher,
            new_status=AppointmentStatus.COMPLETED,
        )
        self.assertEqual(completed.status, AppointmentStatus.COMPLETED)

        day = _rule_day_ahead(3)
        slot2 = _create_slot(self.teacher, _aware(day, 12, 0), _aware(day, 12, 30))
        appt2 = book_slot(
            student=self.student,
            slot_id=slot2.id,
            session_type=SessionType.RECITATION,
        )
        no_show = mark_appointment_status(
            appt2.id,
            self.teacher,
            new_status=AppointmentStatus.NO_SHOW_STUDENT,
        )
        self.assertEqual(no_show.status, AppointmentStatus.NO_SHOW_STUDENT)

    def test_mark_rejects_invalid_status(self):
        with self.assertRaises(AppointmentError) as ctx:
            mark_appointment_status(
                self.appt.id,
                self.teacher,
                new_status=AppointmentStatus.CONFIRMED,
            )
        self.assertEqual(ctx.exception.code, "invalid_status")


@override_settings(AXES_ENABLED=False)
class AppointmentQueryEfficiencyTests(TestCase):
    def setUp(self):
        self.teacher = _make_teacher("appt_q_t")
        self.student = _make_student_with_balance("appt_q_s")
        day = _rule_day_ahead(2)
        create_availability_rule(
            self.teacher,
            {
                "start_date": day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        slots = list(
            AppointmentSlot.objects.filter(teacher=self.teacher).order_by("start_at")[:3]
        )
        for slot in slots:
            book_slot(
                student=self.student,
                slot_id=slot.id,
                session_type=SessionType.RECITATION,
            )

    def test_list_my_appointments_select_related_query_bound(self):
        qs = student_appointments(self.student, bucket="upcoming")
        with CaptureQueriesContext(connection) as ctx:
            items = list(qs[:3])
            self.assertEqual(len(items), 3)
            for item in items:
                _ = item.slot.start_at
                _ = item.teacher_id
                _ = item.student_id
                _ = item.call_session_id
        self.assertLessEqual(len(ctx.captured_queries), 8)


@override_settings(AXES_ENABLED=False)
class AppointmentApiTests(TestCase):
    def setUp(self):
        call_command("seed_rbac")
        self.teacher = _make_teacher("appt_api_teacher")
        self.student = _make_student_with_balance("appt_api_student")
        self.student2 = _make_student_with_balance("appt_api_student2")
        # Re-sync roles for users created after seed
        call_command("seed_rbac")
        start = _rule_day_ahead(3)
        create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slot = AppointmentSlot.objects.filter(teacher=self.teacher).first()
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    def test_session_types_api(self):
        self._login(self.student)
        resp = self.client.get(
            "/api/v1/appointments/session-types/",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["session_types"])

    def test_upcoming_count_api(self):
        self._login(self.student)
        book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )
        resp = self.client.get(
            "/api/v1/appointments/my/upcoming-count/",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["upcoming_count"], 1)
        self.assertEqual(upcoming_count_for_student(self.student), 1)

    def test_toggle_booking_settings_api(self):
        self._login(self.teacher)
        resp = self.client.post(
            "/api/v1/appointments/teacher/settings/toggle/",
            data={"booking_enabled": False},
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.json()["settings"]["booking_enabled"])

    def test_student_cannot_get_another_students_appointment_detail(self):
        appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )
        self._login(self.student2)
        resp = self.client.get(
            f"/api/v1/appointments/{appt.id}/",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "forbidden")

    def test_summary_and_book_flow(self):
        self._login(self.student)
        summary = self.client.get(
            f"/api/v1/appointments/teachers/{self.teacher.id}/summary/",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(summary.status_code, 200, summary.content)
        body = summary.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["booking_enabled"])

        book = self.client.post(
            "/api/v1/appointments/book/",
            data={
                "slot_id": self.slot.id,
                "session_type": SessionType.NEW_MEMORIZATION,
                "student_notes": "سورة البقرة",
            },
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(book.status_code, 201, book.content)
        data = book.json()
        self.assertEqual(data["appointment"]["status"], AppointmentStatus.CONFIRMED)
        self.assertIn("تُحتسب تكلفة الجلسة", data["appointment"]["booking_cost_notice"])


@override_settings(AXES_ENABLED=False)
class AppointmentRbacPermissionTests(TestCase):
    def test_teacher_has_appointments_nav_student_does_not(self):
        teacher = _make_teacher("appt_rbac_t")
        student = _make_student_with_balance("appt_rbac_s")
        call_command("seed_rbac")

        teacher_role = Role.objects.get(slug="teacher")
        student_role = Role.objects.get(slug="student")
        self.assertTrue(teacher.roles.filter(pk=teacher_role.pk).exists())
        self.assertTrue(student.roles.filter(pk=student_role.pk).exists())

        self.assertTrue(teacher.has_permission("mobile.nav.appointments.view"))
        self.assertFalse(student.has_permission("mobile.nav.appointments.view"))
