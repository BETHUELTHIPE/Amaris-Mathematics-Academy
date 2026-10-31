"""Library permissions, private downloads and document validation without external services."""

import io
import uuid
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from botocore.exceptions import ClientError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .authentication import SupabaseStudentAuthentication
from .library_models import LIBRARY_MAX_BYTES, LibraryResource, validate_library_file


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "public": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }
)
class LibraryTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.storage_override = override_settings(
            MEDIA_ROOT=self.directory.name,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        self.storage_override.enable()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.storage_override.disable)
        self.client = APIClient()
        self.tutor = get_user_model().objects.create_user("tutor", email="tutor@example.test")
        self.tutor.groups.add(Group.objects.create(name="Tutors"))
        self.other = get_user_model().objects.create_user("other", email="other@example.test")
        self.other.groups.add(Group.objects.get(name="Tutors"))
        self.root = get_user_model().objects.create_superuser("root", "root@example.test", "unit-test-password")

    def file(self, name="algebra.pdf", content=b"%PDF-1.7\nSynthetic worksheet\n%%EOF"):
        return SimpleUploadedFile(name, content, content_type="application/octet-stream")

    def data(self, **extra):
        return {
            "title": "Algebra textbook",
            "description": "Practice equations",
            "resource_type": "textbook",
            "subject": "Mathematics",
            "level": "Grade 12",
            "file": self.file(),
            "sharing_permitted": "true",
            **extra,
        }

    def request(self, method, route, data=None, email="tutor@example.test", verified=True, format="multipart"):
        payload = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, email)),
            "email": email,
            "email_confirmed_at": "2026-10-01T12:00:00Z" if verified else None,
        }
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=payload):
            return getattr(self.client, method)(
                route, data=data, format=format, secure=True, HTTP_AUTHORIZATION="Bearer synthetic-test-token"
            )

    def create(self, **extra):
        result = self.request("post", reverse("tutor-library"), self.data(**extra))
        self.assertEqual(result.status_code, 201, result.data)
        return LibraryResource.objects.get(pk=result.data["id"])

    def test_anonymous_and_unverified_users_cannot_read_or_upload(self):
        for route in ("student-library", "tutor-library"):
            self.assertEqual(self.client.get(reverse(route), secure=True).status_code, 401)
            self.assertEqual(self.request("get", reverse(route), verified=False).status_code, 401)
        self.assertEqual(self.client.post(reverse("tutor-library"), self.data(), secure=True).status_code, 401)

    def test_student_and_unapproved_admin_cannot_upload(self):
        for email in ("student@example.test", "root@example.test"):
            result = self.request("post", reverse("tutor-library"), self.data(), email=email)
            self.assertEqual(result.status_code, 401)
        self.assertEqual(LibraryResource.objects.count(), 0)
        self.assertEqual(
            self.request("post", reverse("student-library"), self.data(), email="student@example.test").status_code, 405
        )

    def test_upload_has_server_owned_metadata_and_no_exposed_storage_path(self):
        obj = self.create(uploaded_by=str(self.other.pk), original_name="spoofed", size_bytes="1")
        self.assertEqual(obj.uploaded_by, self.tutor)
        self.assertEqual(obj.original_name, "algebra.pdf")
        self.assertEqual(obj.content_type, "application/pdf")
        self.assertGreater(obj.size_bytes, 1)
        self.assertTrue(obj.file.name.startswith("library/"))
        self.assertNotIn("algebra", obj.file.name)
        result = self.request("get", reverse("student-library"), email="student@example.test")
        item = result.data["results"][0]
        self.assertFalse(item["can_manage"])
        self.assertNotIn("file", item)
        self.assertNotIn("uploaded_by", item)
        self.assertEqual(result["Cache-Control"], "private, no-store")

    def test_student_can_download_exact_uploaded_document(self):
        obj = self.create()
        result = self.request("get", reverse("student-library-download", args=[obj.pk]), email="student@example.test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result["Content-Type"], "application/pdf")
        self.assertIn("attachment", result["Content-Disposition"])
        self.assertIn("algebra.pdf", result["Content-Disposition"])
        self.assertEqual(b"".join(result.streaming_content), b"%PDF-1.7\nSynthetic worksheet\n%%EOF")
        self.assertEqual(result["Cache-Control"], "private, no-store")

    def test_cloud_download_is_signed_instead_of_public(self):
        obj = self.create()
        storage = LibraryResource._meta.get_field("file").storage
        with (
            patch.object(storage, "querystring_auth", True, create=True),
            patch.object(
                storage, "url", return_value="https://storage.example.test/signed-document?signature=synthetic"
            ) as sign,
        ):
            result = self.request(
                "get", reverse("student-library-download", args=[obj.pk]), email="student@example.test"
            )
        self.assertEqual(result.status_code, 302)
        self.assertIn("signature=", result["Location"])
        self.assertEqual(sign.call_args.args[0], obj.file.name)
        self.assertIn("attachment", sign.call_args.kwargs["parameters"]["ResponseContentDisposition"])

    def test_hidden_document_is_invisible_to_students_and_other_tutors(self):
        obj = self.create(is_published="false")
        for email, route, download in (
            ("student@example.test", "student-library", "student-library-download"),
            (self.other.email, "tutor-library", "tutor-library-download"),
        ):
            self.assertEqual(self.request("get", reverse(route), email=email).data["count"], 0)
            self.assertEqual(self.request("get", reverse(download, args=[obj.pk]), email=email).status_code, 404)
        own = self.request("get", reverse("tutor-library"))
        self.assertTrue(own.data["results"][0]["can_manage"])
        result = self.request("get", reverse("tutor-library-download", args=[obj.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Synthetic worksheet", b"".join(result.streaming_content))

    def test_tutor_can_only_change_publication_for_own_document(self):
        obj = self.create()
        route = reverse("tutor-library-update", args=[obj.pk])
        denied = self.request("patch", route, {"is_published": False}, email=self.other.email, format="json")
        self.assertEqual(denied.status_code, 404)
        own = self.request(
            "patch", route, {"is_published": False, "uploaded_by": self.other.pk, "title": "spoof"}, format="json"
        )
        self.assertEqual(own.status_code, 200)
        obj.refresh_from_db()
        self.assertFalse(obj.is_published)
        self.assertEqual(obj.title, "Algebra textbook")
        self.assertEqual(obj.uploaded_by, self.tutor)
        published = self.request("patch", route, {"is_published": True}, format="json")
        self.assertTrue(published.data["is_published"])
        self.assertEqual(self.request("get", reverse("student-library"), email="student@example.test").data["count"], 1)

    def test_missing_or_false_permission_is_rejected(self):
        for value in ("false", ""):
            self.assertEqual(
                self.request("post", reverse("tutor-library"), self.data(sharing_permitted=value)).status_code, 400
            )
        data = self.data()
        del data["sharing_permitted"]
        self.assertEqual(self.request("post", reverse("tutor-library"), data).status_code, 400)
        obj = LibraryResource(sharing_permitted=False)
        with self.assertRaises(ValidationError):
            obj.clean()

    def test_rejects_empty_oversized_unsupported_and_spoofed_documents(self):
        for file in (
            self.file("script.html", b"<html>"),
            self.file("algebra.pdf", b"<script>"),
            self.file("empty.pdf", b""),
            self.file("bad.txt", b"\x00\xff"),
            self.file("bad.docx", b"not a zip"),
        ):
            result = self.request("post", reverse("tutor-library"), self.data(file=file))
            self.assertEqual(result.status_code, 400, result.data)
        file = self.file()
        file.size = LIBRARY_MAX_BYTES + 1
        with self.assertRaises(ValidationError):
            validate_library_file(file)
        self.assertEqual(LibraryResource.objects.count(), 0)

    def test_office_document_types_match_container_and_macros_are_rejected(self):
        for name, path in (
            ("notes.docx", "word/document.xml"),
            ("sheet.xlsx", "xl/workbook.xml"),
            ("slides.pptx", "ppt/presentation.xml"),
        ):
            out = io.BytesIO()
            with ZipFile(out, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr(path, "<document/>")
            validate_library_file(self.file(name, out.getvalue()))
            with self.assertRaises(ValidationError):
                validate_library_file(
                    self.file("mismatch.docx" if name.endswith("xlsx") else "mismatch.xlsx", out.getvalue())
                )
        out = io.BytesIO()
        with ZipFile(out, "w") as archive:
            for path in ("[Content_Types].xml", "word/document.xml", "word/vbaProject.bin"):
                archive.writestr(path, "test")
        with self.assertRaises(ValidationError):
            validate_library_file(self.file("macro.docx", out.getvalue()))

    def test_search_type_filter_and_bounded_pagination(self):
        first = self.create()
        for index in range(25):
            LibraryResource.objects.create(
                title=f"Geometry {index}",
                resource_type="worksheet",
                subject="Mathematics",
                level="Grade 10",
                file=first.file.name,
                size_bytes=first.size_bytes,
                original_name="same.pdf",
                content_type="application/pdf",
                sharing_permitted=True,
                uploaded_by=self.tutor,
            )
        url = reverse("student-library")
        self.assertEqual(len(self.request("get", url).data["results"]), 24)
        self.assertEqual(len(self.request("get", url + "?page=2").data["results"]), 2)
        self.assertEqual(self.request("get", url + "?page=invalid").data["page"], 1)
        self.assertEqual(self.request("get", url + "?q=grade+12&resource_type=textbook").data["count"], 1)
        self.assertEqual(self.request("get", url + "?q=Geometry&resource_type=worksheet").data["count"], 25)

    def test_storage_failure_is_retryable_and_creates_no_record(self):
        storage = LibraryResource._meta.get_field("file").storage
        error = ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "synthetic"}}, "PutObject")
        with patch.object(storage, "save", side_effect=error):
            response = self.request("post", reverse("tutor-library"), self.data())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(LibraryResource.objects.count(), 0)

    def test_django_admin_upload_and_hidden_download(self):
        self.client.force_login(self.root)
        response = self.client.post(
            reverse("admin:content_libraryresource_add"), self.data(is_published=""), secure=True
        )
        self.assertEqual(response.status_code, 302, response.content[:1200])
        obj = LibraryResource.objects.get()
        self.assertEqual(obj.uploaded_by, self.root)
        self.assertFalse(obj.is_published)
        download = self.client.get(reverse("admin:content_libraryresource_download", args=[obj.pk]), secure=True)
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"Synthetic worksheet", b"".join(download.streaming_content))
        self.assertEqual(admin.site._registry[LibraryResource].model._meta.verbose_name_plural, "Library")

    def test_admin_download_requires_model_permission(self):
        obj = self.create()
        staff = get_user_model().objects.create_user("limited", is_staff=True)
        self.client.force_login(staff)
        route = reverse("admin:content_libraryresource_download", args=[obj.pk])
        self.assertEqual(self.client.get(route, secure=True).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_libraryresource"))
        result = self.client.get(route, secure=True)
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Synthetic worksheet", b"".join(result.streaming_content))
