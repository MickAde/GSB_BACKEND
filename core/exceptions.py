import logging
from django.utils import timezone
from rest_framework.views import exception_handler
from rest_framework import status

logger = logging.getLogger(__name__)

_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST:            'BAD_REQUEST',
    status.HTTP_401_UNAUTHORIZED:           'UNAUTHORIZED',
    status.HTTP_403_FORBIDDEN:              'FORBIDDEN',
    status.HTTP_404_NOT_FOUND:              'NOT_FOUND',
    status.HTTP_405_METHOD_NOT_ALLOWED:     'METHOD_NOT_ALLOWED',
    status.HTTP_409_CONFLICT:               'CONFLICT',
    status.HTTP_422_UNPROCESSABLE_ENTITY:   'VALIDATION_ERROR',
    status.HTTP_429_TOO_MANY_REQUESTS:      'RATE_LIMIT_EXCEEDED',
    status.HTTP_500_INTERNAL_SERVER_ERROR:  'INTERNAL_SERVER_ERROR',
    status.HTTP_503_SERVICE_UNAVAILABLE:    'SERVICE_UNAVAILABLE',
}


def gsb_exception_handler(exc, context):
    """
    RFC 7807-compliant error envelope for every API error.

    All backend errors conform to:
      { error_code, detail, status_code, timestamp }
    """
    response = exception_handler(exc, context)

    if response is None:
        logger.exception('Unhandled exception in view %s', context.get('view'))
        return response

    http_status = response.status_code
    error_code = _STATUS_TO_CODE.get(http_status, 'ERROR')

    raw = response.data
    if isinstance(raw, dict):
        detail = raw.get('detail', str(raw))
    elif isinstance(raw, list):
        detail = '; '.join(str(item) for item in raw)
    else:
        detail = str(raw)

    response.data = {
        'error_code': error_code,
        'detail': str(detail),
        'status_code': http_status,
        'timestamp': timezone.now().isoformat(),
    }

    return response
