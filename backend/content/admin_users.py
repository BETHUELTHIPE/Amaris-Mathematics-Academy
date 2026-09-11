from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import PermissionDenied

from .rbac import (
    ROLE_ADMINISTRATOR,
    ROLE_STUDENT,
    ROLE_SUPER_ADMINISTRATOR,
    ROLE_TUTOR,
    assign_role,
    user_has_role,
)

User = get_user_model()
MANAGED_ROLES = (
    (ROLE_STUDENT, "Student"),
    (ROLE_TUTOR, "Tutor"),
    (ROLE_ADMINISTRATOR, "Administrator"),
    (ROLE_SUPER_ADMINISTRATOR, "Super Administrator"),
)


def _is_super_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user_has_role(user, ROLE_SUPER_ADMINISTRATOR)))


class SuperAdminUserCreationForm(forms.ModelForm):
    role = forms.ChoiceField(choices=MANAGED_ROLES)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, min_length=12)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, min_length=12)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            assign_role(user, self.cleaned_data["role"])
        return user


class SuperAdminUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Password")
    role = forms.ChoiceField(choices=MANAGED_ROLES, required=False)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "is_active",
            "role",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            for role_name, _label in MANAGED_ROLES:
                if user_has_role(self.instance, role_name):
                    self.fields["role"].initial = role_name
                    break

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit and self.cleaned_data.get("role"):
            assign_role(user, self.cleaned_data["role"])
        return user


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class SuperAdminUserAdmin(DjangoUserAdmin):
    add_form = SuperAdminUserCreationForm
    form = SuperAdminUserChangeForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal information", {"fields": ("first_name", "last_name", "email")}),
        ("Amaris role", {"fields": ("role",)}),
        ("Account status", {"fields": ("is_active",)}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("last_login", "date_joined")
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)

    def has_module_permission(self, request):
        return _is_super_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_super_admin(request.user)

    def has_add_permission(self, request):
        return _is_super_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return _is_super_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        if not _is_super_admin(request.user):
            return False
        if obj is not None and obj.pk == request.user.pk:
            return False
        return True

    def save_model(self, request, obj, form, change):
        if not _is_super_admin(request.user):
            raise PermissionDenied("Only a Super Administrator may manage user accounts.")
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not _is_super_admin(request.user):
            return qs.none()
        return qs
