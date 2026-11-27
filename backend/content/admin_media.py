"""Superuser upload controls in the existing VideoAsset change form."""

import json
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.utils.html import format_html
from urllib.error import URLError

from .models import VideoAsset
from .services.course_media import FOLDER_URL, begin_video_upload, enabled_providers, verify_video_upload


class MediaUploadWidget(forms.HiddenInput):
    @property
    def is_hidden(self):
        return False

    def render(self, name, value, attrs=None, renderer=None):
        hidden = super().render(name, value, attrs, renderer)
        if attrs and attrs.get("data-upload-admin") == "disabled":
            return hidden
        enabled = enabled_providers()
        return format_html(
            '<div data-academy-upload data-asset="{}" data-url="{}" data-s3="{}" data-vimeo="{}">'
            '<label for="academy-video-file">Video file</label> '
            '<input type="file" id="academy-video-file" accept="video/*,.mkv,.mxf,.m4v"> '
            '<button type="button" class="button" data-upload-start>Upload video</button> '
            '<progress data-upload-progress value="0" max="100" hidden></progress> '
            '<p data-upload-status aria-live="polite"></p>'
            '<p class="help">Select S3 or Vimeo under Provider, upload, then save this record. '
            '<a href="{}" target="_blank" rel="noopener noreferrer">Open the academy Vimeo folder</a>.</p>'
            "{}</div>",
            (attrs or {}).get("data-asset", ""),
            reverse("admin:content_videoasset_begin_upload"),
            "yes" if enabled["s3"] else "no",
            "yes" if enabled["vimeo"] else "no",
            FOLDER_URL,
            hidden,
        )


class VideoAssetForm(forms.ModelForm):
    upload_ticket = forms.CharField(label="Direct video upload", required=False, widget=MediaUploadWidget)

    class Meta:
        model = VideoAsset
        fields = "__all__"

    class Media:
        js = ("content/admin-course-media.js",)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.asset_id = "" if self.instance._state.adding else str(self.instance.pk)
        widget = self.fields["upload_ticket"].widget
        widget.attrs["data-asset"] = self.asset_id
        if not user or not user.is_superuser:
            widget.attrs["data-upload-admin"] = "disabled"
        self.original_provider = self.instance.provider if self.asset_id else ""
        if enabled_providers()["s3"] and getattr(user, "is_superuser", False):
            # Keep the old file reference intact while new assets use direct AWS uploads.
            self.fields["source_file"].disabled = True

    def clean(self):
        data = super().clean()
        provider = data.get("provider")
        ticket = data.get("upload_ticket")
        if ticket:
            if not self.user or not self.user.is_superuser:
                raise ValidationError("Only the super admin can upload directly to S3 or Vimeo.")
            if provider not in ("s3", "vimeo"):
                raise ValidationError("Choose the destination used for this upload.")
            reference = verify_video_upload(ticket, user_id=self.user.pk, asset_id=self.asset_id, provider=provider)
            if provider == "s3":
                self.instance.aws_media_key = reference
            else:
                self.instance.vimeo_video_id = reference
        elif provider in ("s3", "vimeo") and provider != self.original_provider and enabled_providers().get(provider):
            raise ValidationError("Upload a video to the selected destination before saving.")
        return data


def begin_admin_upload(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method != "POST":
        return JsonResponse({"error": "Use POST to start an upload."}, status=405)
    if len(request.body) > 4096:
        return JsonResponse({"error": "Invalid upload details."}, status=400)
    try:
        data = json.loads(request.body)
        provider, filename, title, asset = (data[key] for key in ("provider", "filename", "title", "asset"))
        if not (
            isinstance(title, str)
            and 0 < len(title.strip()) <= 180
            and isinstance(filename, str)
            and 0 < len(filename) <= 255
            and isinstance(asset, str)
        ):
            raise ValueError
        if asset and not VideoAsset.objects.filter(pk=UUID(asset)).exists():
            raise ValueError
        response = begin_video_upload(
            user_id=request.user.pk,
            asset_id=asset,
            provider=provider,
            filename=filename,
            size=data["size"],
            title=title.strip(),
        )
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"error": "Invalid upload details."}, status=400)
    except (BotoCoreError, ClientError, URLError, TimeoutError):
        return JsonResponse({"error": "The upload provider is temporarily unavailable."}, status=502)
    return JsonResponse(response)
