import logging
from django.conf import settings
from django.db import connection, transaction

from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import set_current_school_id

logger = logging.getLogger(__name__)

_IS_POSTGRES = (
    settings.DATABASES.get('default', {}).get('ENGINE') == 'django.db.backends.postgresql'
)


class TenantMiddleware:
    """
    Extracts school_id from the JWT Bearer token on every request and:

    1. Stores it in thread-local storage so TenantManager can filter ORM queries.
    2. On PostgreSQL: injects it as a transaction-local session variable
       (SET LOCAL "app.current_school_id") so the database-level RLS policies
       can independently enforce tenant isolation — even against raw SQL.

    The SET LOCAL variable is automatically destroyed when the wrapping
    transaction closes at the end of the request, leaving zero residue.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        school_id = self._extract_school_id(request)
        request.school_id = school_id
        set_current_school_id(school_id)

        try:
            if school_id and _IS_POSTGRES:
                response = self._call_with_rls(request, school_id)
            else:
                response = self.get_response(request)
        finally:
            # Always clean up — prevents tenant context leaking across requests
            # in thread-pool environments.
            set_current_school_id(None)

        return response

    def _call_with_rls(self, request, school_id):
        with transaction.atomic():
            with connection.cursor() as cursor:
                # set_config(name, value, is_local=true) is equivalent to SET LOCAL
                # and is safe against SQL injection via parameterised call.
                cursor.execute(
                    "SELECT set_config('app.current_school_id', %s, true)",
                    [str(school_id)],
                )
            return self.get_response(request)

    def _extract_school_id(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = AccessToken(raw_token)
            return token.get('school_id')  # None for Visitor accounts
        except (InvalidToken, TokenError):
            return None
