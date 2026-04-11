# ===============================================================
#  backend/settings.py
#  Central configuration for the entire Django project
#
#  SECTION MAP:
#  Step 0  → Imports & .env loading
#  Step 1  → Core security settings (SECRET_KEY, DEBUG, ALLOWED_HOSTS)
#  Step 2  → Installed apps
#  Step 3  → Middleware stack
#  Step 4  → REST Framework + JWT config
#  Step 5  → CORS (Next.js cross-origin access)
#  Step 6  → Authentication backends
#  Step 7  → Media files (local dev fallback)
#  Step 8  → Email (SMTP via Gmail)
#  Step 9  → Google OAuth (Calendar integration)
#  Step 10 → MinIO / S3 file storage
#  Step 11 → Custom User model
#  Step 12 → Templates
#  Step 13 → Database (PostgreSQL + pgvector)
#  Step 14 → Password validators
#  Step 15 → Internationalisation & timezone
#  Step 16 → Static files
#  Step 17 → Auth redirect URLs
# ===============================================================


# ---------------- Step 0: Imports & Environment ----------------
import os
from pathlib import Path
from dotenv import load_dotenv  # Reads key=value pairs from a .env file into os.environ
from datetime import timedelta

load_dotenv()  # Must run before any os.getenv() calls so .env values are available

# BASE_DIR points to the project root (the folder containing manage.py)
# Used throughout settings to build absolute paths (e.g., BASE_DIR / 'media')
BASE_DIR = Path(__file__).resolve().parent.parent


# ================================================================
#  Step 1: Core Security Settings
#  These three values are the most critical for production safety
# ================================================================

# SECRET_KEY signs cookies, CSRF tokens, and session data
# NEVER hardcode this — always load from environment
SECRET_KEY = os.getenv("SECRET_KEY")

# DEBUG=True → detailed error pages, Django serves static/media files
# DEBUG=False → generic error pages, suitable for production
# Reads "True"/"False" string from .env and converts to Python bool
DEBUG = os.getenv("DEBUG", "False") == "True"

# Only these hostnames are allowed to serve the Django app
# In production: your domain (e.g., "api.chronoassist.com")
# Multiple hosts can be set via comma-separated values in .env
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")


# ================================================================
#  Step 2: Installed Apps
#  Order matters — Django loads apps top-to-bottom
#  django.contrib.* → built-in Django features
#  Third-party apps  → rest_framework, corsheaders, storages
#  Your apps         → authapp, file_upload, rbac, mail, calendar_app, tasks
# ================================================================
INSTALLED_APPS = [
    # ---------------- Django Built-ins ----------------
    'django.contrib.admin',        # Admin panel at /admin/
    'django.contrib.auth',         # Authentication framework (User model, login, permissions)
    'django.contrib.contenttypes', # Tracks all installed models (used by permissions system)
    'django.contrib.sessions',     # Session storage (used by login() to persist auth state)
    'django.contrib.messages',     # Flash messages framework
    'django.contrib.staticfiles',  # Collects and serves static assets

    # ---------------- Your Apps ----------------
    'authapp',       # Custom User model, registration, login, OTP, RBAC user management
    'mail',          # Email features
    'file_upload',   # Document upload, embedding pipeline, RAG chat
    'calendar_app',  # Google Calendar OAuth + event management
    'tasks',         # Task management
    'rbac',          # Role-Based Access Control (roles + permissions)

    # ---------------- Third-Party ----------------
    'rest_framework', # Django REST Framework — provides @api_view, serializers, permissions
    'corsheaders',    # Allows Next.js (different origin) to make requests to this API
    'storages',       # django-storages: routes FileField writes to MinIO/S3
]


# ================================================================
#  Step 3: Middleware Stack
#  Runs in order for every incoming request (top-to-bottom)
#  and in reverse order for outgoing responses (bottom-to-top)
# ================================================================
MIDDLEWARE = [
    # CorsMiddleware MUST be first — it needs to intercept requests before
    # any other middleware modifies or rejects them (especially preflight OPTIONS)
    'corsheaders.middleware.CorsMiddleware',

    'django.middleware.security.SecurityMiddleware',           # HTTPS redirects, security headers
    'django.contrib.sessions.middleware.SessionMiddleware',    # Loads session from DB on each request
    'django.middleware.common.CommonMiddleware',               # URL normalization (trailing slashes)
    'django.middleware.csrf.CsrfViewMiddleware',               # Validates CSRF token on unsafe methods
    'django.contrib.auth.middleware.AuthenticationMiddleware', # Attaches request.user from session
    'django.contrib.messages.middleware.MessageMiddleware',    # Attaches messages to request
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # Adds X-Frame-Options header (iframe protection)
]


# ================================================================
#  Step 4: REST Framework + JWT Configuration
#  DRF handles API serialization and permission enforcement
#  SimpleJWT provides stateless token authentication as an alternative to sessions
#
#  NOTE: Your main login flow uses Django sessions (login() + OTP).
#  JWT is available as an alternative authentication method
#  (e.g., for mobile clients or third-party integrations).
# ================================================================

# Tells DRF to accept Bearer <token> headers for authentication
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

# Token lifetimes:
# Access token  → short-lived (1 day), used for API requests
# Refresh token → long-lived (7 days), used to get a new access token when it expires
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

ROOT_URLCONF = 'backend.urls'  # Django's URL router starts here


# ================================================================
#  Step 5: CORS (Cross-Origin Resource Sharing)
#  Next.js runs on http://localhost:3000 (different origin than Django's :8000)
#  Without CORS headers, browsers block all cross-origin API requests
# ================================================================

# Only origins listed here are allowed to make cross-origin requests
# In production: set CORS_ALLOWED_ORIGINS=https://app.chronoassist.com in .env
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")

# CORS_ALLOW_CREDENTIALS = True → allows the browser to send cookies (session, CSRF)
# This is required for Django session-based login to work with Next.js
CORS_ALLOW_CREDENTIALS = True


# ================================================================
#  Step 6: Authentication Backends
#  Django calls each backend in order when authenticate() is used
#  First match wins — if a backend returns a user, the rest are skipped
# ================================================================
AUTHENTICATION_BACKENDS = [
    # Custom backend: looks up users by email (not username)
    # Used by login() in views.py and by the Django admin
    'authapp.auth_backend.EmailAuthBackend',

    # Django's default: looks up users by username
    # Kept as fallback for Django internals and any code that passes username=
    'django.contrib.auth.backends.ModelBackend',
]


# ================================================================
#  Step 7: Media Files (Local Development Fallback)
#  In production, MinIO handles all file storage.
#  MEDIA_ROOT/MEDIA_URL are a local fallback for development when MinIO is not running.
#  Files at MEDIA_ROOT are served by Django at /media/ only when DEBUG=True (see urls.py)
# ================================================================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # e.g., /project/backend/media/


# ================================================================
#  Step 8: Email Configuration (SMTP via Gmail)
#  Used by send_otp_email() in authapp/utils.py
#  All sensitive credentials come from .env — never hardcode here
# ================================================================
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")  # Gmail SMTP server
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))           # TLS port
EMAIL_USE_TLS = True                                      # Encrypts the SMTP connection
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")       # The Gmail address that sends emails
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")  # App password (not Gmail login password)


# ================================================================
#  Step 9: Google OAuth Configuration (Calendar App)
#  Used by calendar_app for the Google Calendar OAuth2 flow
#  GOOGLE_REDIRECT_URI must match exactly what's registered in Google Cloud Console
# ================================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/api/calendar/google/callback/"
)


# ================================================================
#  Step 10: MinIO / S3 File Storage
#  MinIO is a self-hosted S3-compatible object store
#  django-storages routes Django FileField writes to MinIO automatically
#
#  Variable mapping:
#   MINIO_* vars → read from .env → aliased to AWS_* vars
#   AWS_* vars   → used by django-storages (S3Boto3Storage) and boto3
# ================================================================

# Read MinIO connection details from .env
MINIO_ENDPOINT_URL = os.environ.get("MINIO_ENDPOINT_URL")   # e.g., http://localhost:9000
MINIO_ACCESS_KEY   = os.environ.get("MINIO_ACCESS_KEY")     # MinIO access key (like AWS key ID)
MINIO_SECRET_KEY   = os.environ.get("MINIO_SECRET_KEY")     # MinIO secret key
MINIO_BUCKET_NAME  = os.environ.get("MINIO_BUCKET_NAME")    # The bucket to store all uploads in

# Tell Django to use S3Boto3Storage as the default file storage backend
# This means any FileField.save() call automatically writes to MinIO
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# Alias MinIO values to the AWS_* names that django-storages and boto3 expect
AWS_S3_ENDPOINT_URL      = MINIO_ENDPOINT_URL
AWS_ACCESS_KEY_ID        = MINIO_ACCESS_KEY
AWS_SECRET_ACCESS_KEY    = MINIO_SECRET_KEY
AWS_STORAGE_BUCKET_NAME  = MINIO_BUCKET_NAME
AWS_S3_USE_SSL           = False  # MinIO runs over HTTP in local dev (no SSL certificate needed)
AWS_S3_VERIFY            = False  # Skip SSL cert verification (safe for local MinIO)

# MinIO-specific compatibility options
AWS_S3_REGION_NAME       = os.getenv("MINIO_REGION", "us-east-1")  # MinIO ignores region but boto3 requires it
AWS_DEFAULT_ACL          = None         # Don't apply any ACL — bucket policy controls access
AWS_S3_ADDRESSING_STYLE  = "path"       # Path-style URLs (http://minio:9000/bucket/key) — required for MinIO
AWS_QUERYSTRING_AUTH     = True         # Presigned URLs include auth query params (not headers)


# ================================================================
#  Step 11: Custom User Model
#  Tells Django to use authapp.User instead of the built-in auth.User
#  MUST be set before the first migration — cannot be changed after
#  All ForeignKey(settings.AUTH_USER_MODEL) references resolve to this
# ================================================================
AUTH_USER_MODEL = "authapp.User"


# ================================================================
#  Step 12: Templates
#  Django's template engine config
#  APP_DIRS=True → auto-discovers templates/ folder in each installed app
#  context_processors → injects request, auth user, and messages into every template
# ================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],        # No project-level template directories
        'APP_DIRS': True,  # Look for templates/ inside each app
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',  # Adds `request` to template context
                'django.contrib.auth.context_processors.auth', # Adds `user` and `perms` to context
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'  # Entry point for production WSGI servers (Gunicorn, uWSGI)


# ================================================================
#  Step 13: Database (PostgreSQL)
#  Uses PostgreSQL for:
#   - All Django models (User, Document, Role, etc.)
#   - pgvector extension (DocumentChunk.embedding VectorField)
#  All connection values come from .env to keep credentials out of source control
# ================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',  # PostgreSQL driver
        'NAME':     os.getenv("DB_NAME", "chrono"),
        'USER':     os.getenv("DB_USER", "postgres"),
        'PASSWORD': os.getenv("DB_PASSWORD", ""),
        'HOST':     os.getenv("DB_HOST", "127.0.0.1"),
        'PORT':     os.getenv("DB_PORT", "5432"),
    }
}


# ================================================================
#  Step 14: Password Validators
#  Enforced when User.set_password() is called (during registration)
#  Four built-in validators:
#   1. UserAttributeSimilarity → rejects passwords too similar to username/email
#   2. MinimumLength           → rejects passwords shorter than 8 chars (default)
#   3. CommonPassword          → rejects passwords on the common passwords list
#   4. NumericOnly             → rejects passwords that are entirely numbers
# ================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ================================================================
#  Step 15: Internationalisation & Timezone
#  USE_TZ=True → all datetimes are stored in UTC in the database
#  This is critical for OTP expiry comparisons in verify_otp_api
#  (timezone.now() returns UTC-aware datetime, matching stored values)
# ================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True   # Enables Django's translation framework
USE_TZ = True     # All DateTimeField values are timezone-aware (UTC)


# ================================================================
#  Step 16: Static Files
#  CSS/JS/images for the Django admin panel
#  Run `python manage.py collectstatic` to gather all static files into STATIC_ROOT
#  In production, a web server (Nginx) serves them from STATIC_ROOT directly
# ================================================================
STATIC_URL = 'static/'

# Default primary key type for models that don't specify one
# BigAutoField = 64-bit integer (supports more rows than the default 32-bit AutoField)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ================================================================
#  Step 17: Auth Redirect URLs
#  Used by Django's built-in auth views (login_required decorator, admin redirects)
#  These have no effect on your DRF API views but are needed for the admin panel flow
# ================================================================
LOGIN_URL = '/accounts/login'          # Where @login_required redirects unauthenticated users
LOGIN_REDIRECT_URL = '/authapp/'       # Where Django redirects after a successful admin login
LOGOUT_REDIRECT_URL = '/authapp/'      # Where Django redirects after logout