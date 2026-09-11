from __future__ import annotations

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType

from .models import (
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    ResourceAsset,
    VideoAsset,
)

ROLE_STUDENT = "Student"
ROLE_TUTOR = "Tutor"
ROLE_ADMINISTRATOR = "Administrator"
ROLE_SUPER_ADMINISTRATOR = "Super Administrator"

ROLE_NAMES = (
    ROLE_STUDENT,
    ROLE_TUTOR,
    ROLE_ADMINISTRATOR,
    ROLE_SUPER_ADMINISTRATOR,
)

TUTOR_CONTENT_MODELS = (
    CourseCategory,
    Course,
    CourseModule,
    Lesson,
    VideoAsset,
    ResourceAsset,
)

TUTOR_PERMISSION_ACTIONS = ("view", "add", "change")


def ensure_role_groups() -> dict[str, Group]:
    groups = {name: Group.objects.get_or_create(name=name)[0] for name in ROLE_NAMES}

    tutor_permissions: list[Permission] = []
    for model in TUTOR_CONTENT_MODELS:
        content_type = ContentType.objects.get_for_model(model)
        for action in TUTOR_PERMISSION_ACTIONS:
            codename = f"{action}_{model._meta.model_name}"
            permission = Permission.objects.get(content_type=content_type, codename=codename)
            tutor_permissions.append(permission)

    groups[ROLE_TUTOR].permissions.set(tutor_permissions)
    return groups


def assign_role(user: User, role_name: str) -> None:
    if role_name not in ROLE_NAMES:
        raise ValueError(f"Unsupported role: {role_name}")

    groups = ensure_role_groups()
    user.groups.remove(*Group.objects.filter(name__in=ROLE_NAMES))
    user.groups.add(groups[role_name])

    if role_name == ROLE_STUDENT:
        user.is_staff = False
        user.is_superuser = False
    elif role_name == ROLE_TUTOR:
        user.is_staff = True
        user.is_superuser = False
    elif role_name == ROLE_ADMINISTRATOR:
        user.is_staff = True
        user.is_superuser = False
    elif role_name == ROLE_SUPER_ADMINISTRATOR:
        user.is_staff = True
        user.is_superuser = True

    user.save(update_fields=["is_staff", "is_superuser"])


def user_has_role(user: User, role_name: str) -> bool:
    if not user.is_authenticated:
        return False
    if role_name == ROLE_SUPER_ADMINISTRATOR and user.is_superuser:
        return True
    return user.groups.filter(name=role_name).exists()
