from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from core.utils.pagination import paginate_with_smart_pages
from ..models import Role
from .common import users_qs
from identity.rbac.decorators import permission_required
from .common import (
    users_qs,
    roles_qs,
    permissions_qs,   
)


# Protected role slugs that must not be deleted or have their slug changed
PROTECTED_ROLE_SLUGS = ("admin", "superadmin")


@permission_required("roles.list")
def roles_list(request):
    tab = "roles"

    users = users_qs()
    permissions = permissions_qs()
    roles_queryset = roles_qs()

    page_obj, roles_page_numbers, per_page_param, total_roles = paginate_with_smart_pages(
        request=request,
        queryset=roles_queryset,
        # تقدر تغيّر الافتراضي هنا إذا حاب (مثلاً "5")
        default_per_page="5",
    )

    context = {
        "tab": tab,
        "users": users,
        "roles": page_obj,
        "roles_page_numbers": roles_page_numbers,
        "permissions": permissions,
        "per_page": per_page_param,
        "total_roles": total_roles,
        "selected_role": None,
        "selected_role_perm_ids": [],
        "message": None,
    }
    return render(request, "rbac/roles/roles.html", context)


@permission_required("roles.create")
def role_create(request):
    """
    Create a new role.
    """
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        slug = (request.POST.get("slug") or "").strip()
        description = (request.POST.get("description") or "").strip()

        if not name or not slug:
            messages.error(request, "الرجاء إدخال اسم الدور والكود.")
        else:
            # Normalize slug to be safer and more consistent
            slug = slug.lower()

            # Check slug uniqueness before creating
            if Role.objects.filter(slug=slug).exists():
                messages.error(request, "كود الدور مستخدم مسبقًا، الرجاء اختيار كود آخر.")
            else:
                Role.objects.create(
                    name=name,
                    slug=slug,
                    description=description,
                )
                messages.success(request, "تم إنشاء الدور بنجاح.")
                return redirect("rbac:roles_list")

    context = {
        "tab": "roles",
        "mode": "create",
    }
    return render(request, "rbac/roles/role_form.html", context)


@permission_required("roles.update")
def role_update(request, pk):
    """
    Update an existing role.
    """
    role = get_object_or_404(Role, pk=pk)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        slug = (request.POST.get("slug") or "").strip()
        description = (request.POST.get("description") or "").strip()

        if not name or not slug:
            messages.error(request, "الرجاء إدخال اسم الدور والكود.")
        else:
            slug = slug.lower()

            # If this is a protected role, do not allow changing the slug
            if role.slug in PROTECTED_ROLE_SLUGS and slug != role.slug:
                messages.error(
                    request,
                    "لا يمكن تعديل الكود لهذا الدور الأساسي."
                )
            else:
                # Check slug uniqueness for this role
                if Role.objects.exclude(pk=role.pk).filter(slug=slug).exists():
                    messages.error(request, "كود الدور مستخدم مسبقًا، الرجاء اختيار كود آخر.")
                else:
                    role.name = name
                    role.slug = slug
                    role.description = description
                    role.save()
                    messages.success(request, "تم تعديل الدور بنجاح.")
                    return redirect("rbac:roles_list")

    context = {
        "tab": "roles",
        "title": "تعديل دور",
        "mode": "edit",
        "initial": {
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
        },
        "role": role,
    }

    return render(request, "rbac/roles/role_form.html", context)


@permission_required("roles.delete")
def role_delete(request, pk):
    """
    Delete an existing role after confirmation.
    Protected roles (admin, superadmin, etc.) cannot be deleted.
    """
    role = get_object_or_404(Role, pk=pk)

    # Block delete for protected roles (both GET and POST)
    if role.slug in PROTECTED_ROLE_SLUGS:
        messages.error(request, "لا يمكن حذف هذا الدور الأساسي.")
        return redirect("rbac:roles_list")

    if request.method == "POST":
        role.delete()
        messages.success(request, "تم حذف الدور بنجاح.")
        return redirect("rbac:roles_list")

    context = {
        "tab": "roles",
        "role": role,
    }
    return render(request, "rbac/roles/role_delete.html", context)
