from pathlib import Path
from datetime import timedelta
from decouple import Config, RepositoryEnv, AutoConfig, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env.local first (local dev), fall back to .env (CI/Docker already injects vars)
_env_local = BASE_DIR / '.env.local'
config = Config(RepositoryEnv(str(_env_local))) if _env_local.exists() else AutoConfig()

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# ── Application Definition ────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_celery_results',
    'django_celery_beat',
    'django_filters',
    'drf_spectacular',

    # Local apps
    'core.apps.CoreConfig',
    'schools.apps.SchoolsConfig',
    'users.apps.UsersConfig',
    'notes.apps.NotesConfig',
    'ai_app.apps.AiAppConfig',
    'quiz.apps.QuizConfig',
    'teaching.apps.TeachingConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'GSB_Project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'GSB_Project.wsgi.application'

# ── Database ──────────────────────────────────────────────────
DB_ENGINE = config('DB_ENGINE', default='sqlite')

if DB_ENGINE == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {
                'sslmode': 'require',
                'connect_timeout': 10,
                # Port MUST be 5432 (direct session connection).
                # Port 6543 is PgBouncer transaction mode — it destroys SET LOCAL
                # session variables between queries, silently breaking our RLS policies.
            },
            'CONN_MAX_AGE': config('CONN_MAX_AGE', default=600, cast=int),
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ── Auth ──────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    'users.backends.GSBAuthBackend',
]

# GSBArgon2Hasher is defined in core/hashers.py with memory_cost=32768 (32 MB).
# Django's default Argon2PasswordHasher uses 100 MB which causes allocation errors
# on constrained development machines. Fallback hashers handle legacy hashes.
PASSWORD_HASHERS = [
    'core.hashers.GSBArgon2Hasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── DRF ───────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '100/minute',
        'auth': '5/minute',        # Login / register endpoints
        'ai_generation': '10/minute',  # AI quiz / summary endpoints
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'core.exceptions.gsb_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardResultsPagination',
    'PAGE_SIZE': 20,
}

# ── JWT ───────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    # school_id and role are injected at token creation time (see users/tokens.py)
}

# ── OpenAPI / Swagger ─────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'Genius Study Buddy API',
    'DESCRIPTION': (
        'Multi-tenant AI-powered educational platform API. '
        'All school-scoped endpoints require a Bearer JWT token. '
        'The JWT payload embeds `school_id` and `role` which drive '
        'row-level security at the database kernel.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,

    # Group endpoints by app tag
    'SCHEMA_PATH_PREFIX': r'/api/v1/',
    'COMPONENT_SPLIT_REQUEST': True,

    # Security scheme — tells Swagger UI to send Bearer tokens.
    # BearerAuth is also defined in APPEND_COMPONENTS below so it appears
    # in securitySchemes and Swagger UI can actually use it.
    'SECURITY': [{'BearerAuth': []}],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': (
                    'JWT obtained from POST /api/v1/auth/login/. '
                    'The payload embeds `role` and `school_id` which drive '
                    'row-level security at the database kernel.'
                ),
            }
        }
    },
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
        'displayRequestDuration': True,
        'filter': True,
        'tryItOutEnabled': True,
    },
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
    ],
    'ENUM_GENERATE_CHOICE_DESCRIPTION': True,
    'ENUM_NAME_OVERRIDES': {
        'NoteTypeEnum':          'notes.models.NoteType',
        'NoteStatusEnum':        'notes.models.NoteStatus',
        'ConformityStatusEnum':  'notes.models.ConformityStatus',
        'UserRoleEnum':          'users.models.UserRole',
        'CreatableUserRoleEnum': 'users.models.CreatableUserRole',
    },
    'CONTACT': {
        'name': 'GSB Engineering',
        'email': 'mickade35@gmail.com',
    },
    'LICENSE': {'name': 'Proprietary'},
    'SERVERS': [
        {'url': 'http://localhost:8000', 'description': 'Local development'},
        {'url': 'https://api.geniusstudybuddy.com', 'description': 'Production'},
    ],
}

# ── CORS ──────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://localhost:5173,https://gsbfrontend.vercel.app',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False  # Never wildcard in any environment

# ── Celery ────────────────────────────────────────────────────
_REDIS_URL = config('REDIS_URL', default='')

# Run tasks eagerly (in-process) when no Redis URL is configured (local dev
# without a broker). An explicit CELERY_TASK_ALWAYS_EAGER env var always wins.
_eager_default = not bool(_REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=_eager_default, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = False   # never propagate — let views handle errors

CELERY_BROKER_URL = _REDIS_URL or 'redis://localhost:6379/1'
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ROUTES = {
    'notes.tasks.run_ocr_pipeline':          {'queue': 'celery_ocr'},
    'ai_app.tasks.run_ai_summary':           {'queue': 'celery_ai'},
    'quiz.tasks.generate_quiz_questions':    {'queue': 'celery_ai'},
    'core.tasks.*':                          {'queue': 'celery_default'},
}

# ── Supabase Storage ──────────────────────────────────────────
# Used for all file uploads (notes, avatars, teacher resources, etc.)
# The service_role key bypasses RLS on the storage bucket — keep it server-side only.
SUPABASE_URL = config('SUPABASE_URL', default='')
SUPABASE_ANON_KEY = config('SUPABASE_ANON_KEY', default='')
SUPABASE_SERVICE_ROLE_KEY = config('SUPABASE_SERVICE_ROLE_KEY', default='')

# Bucket names — create these in Supabase Dashboard > Storage
SUPABASE_NOTES_BUCKET   = config('SUPABASE_NOTES_BUCKET',   default='gsb-notes')
SUPABASE_AVATARS_BUCKET = config('SUPABASE_AVATARS_BUCKET', default='gsb-avatars')

# Local media fallback (used when SUPABASE_URL is not set, e.g. unit tests)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── AI Services ───────────────────────────────────────────────
# Anthropic — Claude (long-form analysis, coding, creative writing)
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
ANTHROPIC_MODEL   = config('ANTHROPIC_MODEL',   default='claude-sonnet-4-6')

# OpenAI — ChatGPT (text) + DALL-E 3 (images)
OPENAI_API_KEY    = config('OPENAI_API_KEY',    default='')
OPENAI_MODEL      = config('OPENAI_MODEL',      default='gpt-4o')
OPENAI_IMAGE_MODEL = config('OPENAI_IMAGE_MODEL', default='dall-e-3')

# Google — Gemini (multimodal, Google Workspace)
GEMINI_API_KEY    = config('GEMINI_API_KEY',    default='')
GEMINI_MODEL      = config('GEMINI_MODEL',      default='gemini-3-flash-preview')

# Perplexity — Search / research with live citations
PERPLEXITY_API_KEY = config('PERPLEXITY_API_KEY', default='')
PERPLEXITY_MODEL   = config('PERPLEXITY_MODEL',   default='sonar')

# Default provider per capability — override per task or per request
AI_DEFAULT_TEXT_PROVIDER   = config('AI_DEFAULT_TEXT_PROVIDER',   default='anthropic')
AI_DEFAULT_IMAGE_PROVIDER  = config('AI_DEFAULT_IMAGE_PROVIDER',  default='openai')
AI_DEFAULT_SEARCH_PROVIDER = config('AI_DEFAULT_SEARCH_PROVIDER', default='perplexity')
# Vision/OCR provider for image transcription (lesson doc uploads, student note images)
# Options: anthropic | openai | gemini
AI_VISION_PROVIDER         = config('AI_VISION_PROVIDER',         default='anthropic')
# Audio transcription provider for voice note uploads
# Options: openai (Whisper — best accuracy) | gemini
AI_AUDIO_PROVIDER          = config('AI_AUDIO_PROVIDER',          default='openai')

# ── Email ─────────────────────────────────────────────────────
# Console backend for local dev; override EMAIL_BACKEND in .env.production
# to django.core.mail.backends.smtp.EmailBackend
EMAIL_BACKEND      = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST         = config('EMAIL_HOST',         default='smtp.sendgrid.net')
EMAIL_PORT         = config('EMAIL_PORT',         default=587, cast=int)
EMAIL_HOST_USER    = config('EMAIL_HOST_USER',    default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS      = config('EMAIL_USE_TLS',      default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@geniusstudybuddy.com')
# Base URL of the frontend app — embedded in password-reset / email-verify links
FRONTEND_URL       = config('FRONTEND_URL', default='http://localhost:3000')

# ── Static Files ──────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Internationalisation ──────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Security Headers (enforced in production) ─────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

# ── Tesseract (Windows) ───────────────────────────────────────
_tesseract_cmd = config('TESSERACT_CMD', default='')
if _tesseract_cmd:
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
    except ImportError:
        pass

# ── Logging ───────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'core': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
        'users': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
        'notes': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
    },
}
