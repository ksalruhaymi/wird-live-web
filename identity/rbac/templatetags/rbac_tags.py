from django import template

from identity.accounts.user_types import user_type_label

register = template.Library()


@register.simple_tag(takes_context=True)
def has_permission(context, code: str) -> bool:
    """
    تاج (Template Tag)
    ------------------
    الغرض:
    - التحقق من الصلاحية باستخدام سياق الصفحة (context)
    - مفيد عندما نحتاج الوصول إلى request / user بدون تمريرهم يدويًا

    الاستخدام في القالب:
    {% load rbac_tags %}
    {% has_permission "dashboard.access" as can_manage %}
    {% if can_manage %}
        ...
    {% endif %}
    """
    request = context.get("request")
    if not request:
        return False

    user = request.user
    if not user.is_authenticated:
        return False

    return user.has_permission(code)


@register.filter
def can_access(user, code: str) -> bool:
    """
    فلتر (Template Filter)
    ---------------------
    الغرض:
    - التحقق من الصلاحية مباشرة داخل شرط if
    - أبسط وأقصر للاستخدام في الواجهة

    الاستخدام في القالب:
    {% load rbac_tags %}
    {% if request.user|can_access:"dashboard.access" %}
        ...
    {% endif %}
    """
    if not user.is_authenticated:
        return False

    return user.has_permission(code)


@register.filter
def user_type_display(user) -> str:
    if not user.is_authenticated:
        return ""
    return user_type_label(user)


@register.filter
def can_any(user, codes: str):
    """
    Check if user has ANY permission from a comma-separated list.
    Usage:
        {% if request.user|can_any:"roles.update,roles.delete" %}
    """
    if not user.is_authenticated:
        return False

    codes_list = [c.strip() for c in codes.split(",") if c.strip()]

    for code in codes_list:
        if user.has_permission(code):
            return True

    return False
