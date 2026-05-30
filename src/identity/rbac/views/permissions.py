from collections import defaultdict

from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import permission_required
from ..models import Permission
from .common import permissions_qs


# Protected permission codes that must not be deleted
# or have their codes changed.
PROTECTED_PERMISSION_CODES = (
    "dashboard.access",
    "roles.list",
    "roles.create",
    "roles.update",
    "roles.delete",
    "permissions.list",
    "permissions.create",
    "permissions.update",
    "permissions.delete",
    "permissions.assign_roles",
)


@permission_required("permissions.list")
def permissions_list(request):
    """
    List permissions grouped by module.
    """
    permissions = permissions_qs()

    permissions_by_module = defaultdict(list)
    for perm in permissions:
        module_name = perm.module or "general"
        permissions_by_module[module_name].append(perm)

    context = {
        "permissions_by_module": dict(permissions_by_module),
        "tab": "permissions",
    }
    return render(request, "rbac/permissions/permissions.html", context)



@permission_required("permissions.create")
def permission_create(request):
    """
    Create a new permission.
    - Checks that the code is unique before saving
    - Returns initial values on error
    """
    initial = {
        "code": "",
        "name": "",
        "module": "",
        "description": "",
    }

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        name = (request.POST.get("name") or "").strip()
        module = (request.POST.get("module") or "").strip()
        description = (request.POST.get("description") or "").strip()

        # Normalize code for consistency
        code = code.lower()

        initial = {
            "code": code,
            "name": name,
            "module": module,
            "description": description,
        }

        if not code or not name:
            messages.error(request, "الرجاء إدخال الكود واسم الصلاحية.")
        elif Permission.objects.filter(code=code).exists():
            messages.error(request, "هذا الكود مستخدم بالفعل لصلاحية أخرى.")
        else:
            try:
                Permission.objects.create(
                    code=code,
                    name=name,
                    module=module,
                    description=description,
                )
                messages.success(request, "تم إنشاء الصلاحية بنجاح.")
                return redirect("rbac:permissions_list")
            except IntegrityError:
                # Extra safety in case of DB-level unique constraint
                messages.error(
                    request,
                    "تعذر حفظ الصلاحية بسبب تكرار الكود في قاعدة البيانات."
                )

    context = {
        "mode": "create",
        "initial": initial,
        "title": "إضافة صلاحية",
        "tab": "permissions",
    }
    return render(request, "rbac/permissions/permission_form.html", context)


@permission_required("permissions.update")
def permission_update(request, pk):
    """
    Update an existing permission.
    - Prevent changing code for protected permissions.
    - Ensure code uniqueness when changed.
    """
    permission = get_object_or_404(Permission, pk=pk)

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        name = (request.POST.get("name") or "").strip()
        module = (request.POST.get("module") or "").strip()
        description = (request.POST.get("description") or "").strip()

        if not code or not name:
            messages.error(request, "الرجاء إدخال كود واسم الصلاحية.")
        else:
            # Normalize code
            code = code.lower()

            # Do not allow changing code for protected permissions
            if permission.code in PROTECTED_PERMISSION_CODES and code != permission.code:
                messages.error(
                    request,
                    "لا يمكن تعديل كود هذه الصلاحية الأساسية."
                )
            else:
                # Ensure uniqueness of the code (excluding the current permission)
                if Permission.objects.exclude(pk=permission.pk).filter(code=code).exists():
                    messages.error(request, "هذا الكود مستخدم بالفعل لصلاحية أخرى.")
                else:
                    permission.code = code
                    permission.name = name
                    permission.module = module
                    permission.description = description
                    permission.save()
                    messages.success(request, "تم تعديل الصلاحية بنجاح.")
                    return redirect("rbac:permissions_list")

    context = {
        "tab": "permissions",
        "title": "تعديل صلاحية",
        "mode": "edit",
        "initial": {
            "code": permission.code,
            "name": permission.name,
            "module": permission.module,
            "description": permission.description,
        },
        "permission": permission,
    }

    return render(request, "rbac/permissions/permission_form.html", context)


@permission_required("permissions.delete")
def permission_delete(request, pk):
    """
    Delete an existing permission after confirmation.
    Protected permissions cannot be deleted.
    """
    perm = get_object_or_404(Permission, pk=pk)

    # Block delete for protected permissions (both GET and POST)
    if perm.code in PROTECTED_PERMISSION_CODES:
        messages.error(request, "لا يمكن حذف هذه الصلاحية الأساسية.")
        return redirect("rbac:permissions_list")

    if request.method == "POST":
        perm.delete()
        messages.success(request, "تم حذف الصلاحية بنجاح.")
        return redirect("rbac:permissions_list")

    context = {
        "tab": "permissions",
        "permission": perm,
    }
    return render(request, "rbac/permissions/permission_confirm_delete.html", context)


