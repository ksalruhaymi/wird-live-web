from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from ..decorators import permission_required
from ..models import Role, Permission
from .common import roles_qs, permissions_qs


PROTECTED_ROLE_SLUGS = ("admin", "superadmin")

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



@permission_required("rbac.access")
def rabc_overview(request):
    context = {
        "": "",
    }
    return render(request, "rbac/overview/overview.html", context)


@permission_required("permissions.assign_roles")
def linking_list(request):
    roles = roles_qs()
    permissions = permissions_qs()

    if request.method == "POST":
        action = request.POST.get("action")
        role_id = request.POST.get("role_id")
        perm_id = request.POST.get("perm_id")

        if not role_id or not perm_id:
            messages.error(request, "حدث خطأ في معالجة الطلب: بيانات الدور أو الصلاحية مفقودة.")
            return redirect("rbac:linking_list")

        role = get_object_or_404(Role, pk=role_id)
        perm = get_object_or_404(Permission, pk=perm_id)

        base_url = reverse("rbac:linking_list")

        module = perm.code.split(".", 1)[0] if "." in perm.code else None
        access_perm = None

        if module:
            access_perm = Permission.objects.filter(code=f"{module}.access").first()

        if action == "assign_perm_to_role":
            role.permissions.add(perm)

            if not perm.code.endswith(".access") and access_perm:
                role.permissions.add(access_perm)

            messages.success(request, "تم ربط الصلاحية بالدور بنجاح.")

        elif action == "remove_perm_from_role":
            if role.slug in PROTECTED_ROLE_SLUGS and perm.code in PROTECTED_PERMISSION_CODES:
                messages.error(request, "لا يمكن إزالة هذه الصلاحية الأساسية من هذا الدور.")
            else:
                role.permissions.remove(perm)

                if not perm.code.endswith(".access") and access_perm:
                    remaining_module_perms = role.permissions.filter(
                        code__startswith=f"{module}."
                    ).exclude(code=f"{module}.access").exists()

                    if not remaining_module_perms:
                        role.permissions.remove(access_perm)

                messages.success(request, "تم إزالة الصلاحية من الدور بنجاح.")

        return redirect(f"{base_url}?role={role_id}")

    selected_role_id = request.GET.get("role")
    selected_role = (
        roles.filter(pk=selected_role_id).first()
        if selected_role_id
        else roles.first()
    )

    selected_role_perm_ids = (
        list(selected_role.permissions.values_list("id", flat=True))
        if selected_role
        else []
    )

    context = {
        "tab": "linking",
        "roles": roles,
        "permissions": permissions,
        "selected_role": selected_role,
        "selected_role_perm_ids": selected_role_perm_ids,
    }
    return render(request, "rbac/linking/tab_linking.html", context)