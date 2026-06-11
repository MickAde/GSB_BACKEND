import threading
import uuid
from django.db import models

# ── Thread-local tenant context ───────────────────────────────
# Set by TenantMiddleware on every authenticated request.
# Cleared in the finally block after the response is returned.
_thread_locals = threading.local()


def get_current_school_id():
    return getattr(_thread_locals, 'school_id', None)


def set_current_school_id(school_id):
    _thread_locals.school_id = school_id


# ── Tenant-scoped manager ─────────────────────────────────────
class TenantManager(models.Manager):
    """
    Default manager for all TenantBoundModel subclasses.
    Automatically filters querysets to the current request's school.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        school_id = get_current_school_id()
        if school_id is not None:
            return qs.filter(school_id=school_id)
        return qs


# ── Abstract base models ──────────────────────────────────────
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantBoundModel(TimeStampedModel):
    """
    Abstract base for every model that belongs to a school (tenant).

    Two managers:
      - objects   : tenant-scoped (always use this in views/serializers)
      - unscoped  : raw access for admin, migrations, and superuser operations
    """
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        db_index=True,
        editable=False,
    )

    objects = TenantManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
