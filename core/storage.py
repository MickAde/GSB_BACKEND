"""
Supabase Storage utility.

All file I/O goes through this module. It uses the service_role key so
the server can write to private buckets without being subject to RLS on
the storage layer (our RLS is enforced at the PostgreSQL layer instead).

Usage:
    from core.storage import storage
    url  = storage.upload('gsb-notes', 'school-id/note.pdf', file_bytes, 'application/pdf')
    url  = storage.get_public_url('gsb-notes', 'school-id/note.pdf')
    storage.delete('gsb-notes', ['school-id/note.pdf'])
"""
import logging
import mimetypes
from functools import lru_cache
from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_client():
    """Returns a cached Supabase client (service_role key for server-side ops)."""
    from supabase import create_client
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            'SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set to use Supabase Storage.'
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class SupabaseStorage:
    """Thin wrapper around Supabase Storage for consistent error handling."""

    def upload(self, bucket: str, path: str, file_data: bytes, content_type: str = '', *, upsert: bool = False) -> str:
        """
        Upload a file and return its public URL.
        path should be prefixed with school_id (or user_id) for isolation,
        e.g. '{school_id}/{uuid}-{filename}' or 'avatars/{user_id}.jpg'
        Set upsert=True to overwrite an existing file at the same path.
        """
        if not content_type:
            content_type, _ = mimetypes.guess_type(path)
            content_type = content_type or 'application/octet-stream'

        client = _get_client()
        client.storage.from_(bucket).upload(
            path=path,
            file=file_data,
            file_options={'content-type': content_type, 'upsert': 'true' if upsert else 'false'},
        )
        return self.get_public_url(bucket, path)

    def get_public_url(self, bucket: str, path: str) -> str:
        client = _get_client()
        response = client.storage.from_(bucket).get_public_url(path)
        return response

    def create_signed_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Returns a time-limited signed URL for private buckets."""
        client = _get_client()
        response = client.storage.from_(bucket).create_signed_url(path, expires_in)
        return response['signedURL']

    def download(self, bucket: str, path: str) -> bytes:
        """Download a file from Supabase Storage using the service_role key."""
        client = _get_client()
        return client.storage.from_(bucket).download(path)

    def delete(self, bucket: str, paths: list[str]) -> None:
        client = _get_client()
        client.storage.from_(bucket).remove(paths)

    def ensure_bucket(self, bucket: str, public: bool = False) -> None:
        """Creates the bucket if it doesn't exist. Safe to call on startup."""
        client = _get_client()
        try:
            client.storage.create_bucket(bucket, options={'public': public})
            logger.info('Created Supabase Storage bucket: %s', bucket)
        except Exception as exc:
            if 'already exists' in str(exc).lower() or 'Duplicate' in str(exc):
                pass  # Bucket already created
            else:
                logger.error('Failed to create bucket %s: %s', bucket, exc)
                raise


storage = SupabaseStorage()
