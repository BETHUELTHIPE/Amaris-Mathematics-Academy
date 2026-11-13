from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import TestCase, override_settings

from amaris_cms.storage import RoleMediaStorage
from content.media_paths import video_captions_path, video_source_path, video_thumbnail_path
from content.models import VideoAsset


class MediaBucketOwnershipTests(TestCase):
    def test_tutor_and_admin_media_use_separate_storage_for_all_operations(self):
        tutor = get_user_model().objects.create_user(username="bucket-tutor")
        tutor.groups.add(Group.objects.get_or_create(name="Tutors")[0])
        admin = get_user_model().objects.create_superuser(username="bucket-admin", email="admin@example.test")
        with override_settings(
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                "tutor_private": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            }
        ):
            router = RoleMediaStorage()
            for actor in (tutor, admin):
                video = VideoAsset(uploaded_by=actor)
                for generator in (video_source_path, video_thumbnail_path, video_captions_path):
                    key = generator(video, "sample.pdf")
                    alias = "tutor_private" if actor == tutor else "default"
                    other = "default" if actor == tutor else "tutor_private"
                    saved = router.save(key, ContentFile(b"synthetic file"))
                    self.assertTrue(storages[alias].exists(saved))
                    self.assertFalse(storages[other].exists(saved))
                    with router.open(saved) as content:
                        self.assertEqual(content.read(), b"synthetic file")
                    self.assertEqual(router.size(saved), 14)
                    self.assertTrue(router.exists(saved))
                    router.delete(saved)
                    self.assertFalse(router.exists(saved))
            # Earlier Admin media keys continue to select Admin storage.
            self.assertIs(router.backend("videos/2026/10/legacy.mp4"), storages["default"])
