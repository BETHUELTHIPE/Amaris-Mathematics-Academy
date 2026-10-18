"""Separate, private S3 storage used only for uploaded learning videos.

The callable is serialized in migrations; bucket names and credentials stay in
deployment environment variables rather than migration files.
"""

from django.core.files.storage import storages


def private_video_storage():
    return storages["private_video"]
