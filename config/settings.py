"""
Django settings for config project.
"""

from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False)
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

DEBUG = env("DEBUG")
# Production refuses to start without a real key; only local development gets a throwaway default.
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only") if DEBUG else env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
if env("RENDER_EXTERNAL_HOSTNAME", default=""):  # set by Render, e.g. civicdesk.onrender.com
    ALLOWED_HOSTS.append(env("RENDER_EXTERNAL_HOSTNAME"))
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # e.g. https://usecivicdesk.com

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django_extensions",
    "core",
    "payments",
    "stratas",
    "dockets",
    "documents",
    "inbox",
    "schedule",
    "issues",
    "meetings",
    
    # UI
    "django_cotton",
    "django_cotton_ui",
    "heroicons",
    
    # Mail
    "anymail",
    
    # Auth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

INTERNAL_IPS = ["127.0.0.1"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves collected static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "stratas.middleware.ActiveStrataMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "stratas.context_processors.strata_context",
                "core.dev.dev_tools",
            ],
            "builtins": [
                "heroicons.templatetags.heroicons",
                "core.templatetags.listbox",
            ]
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    'default': env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0 if DEBUG else 60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Vancouver"  # BC product: "today", deadlines and displayed times are Pacific
USE_I18N = True
USE_TZ = True

# Static & Media files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))  # production: a persistent disk

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "core.User"

# Allauth Settings
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'landing'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*']
ACCOUNT_SIGNUP_FORM_CLASS = 'core.forms.CustomSignupForm'
ACCOUNT_ADAPTER = 'core.adapters.AccountAdapter'

# Social account configuration
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("GOOGLE_OAUTH_CLIENT_ID", default=""),
            "secret": env("GOOGLE_OAUTH_SECRET", default=""),
            "key": "",
        },
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        }
    }
}

# Stripe Configuration
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Claude (document summaries and Q&A). Features degrade gracefully when unset.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

# Local dev accounts (core/dev.py): shared password, used only when DEBUG is on.
DEV_ACCOUNT_PASSWORD = env("DEV_ACCOUNT_PASSWORD", default="helloworld")

# Debug Toolbar (DEBUG_TOOLBAR=False in .env to hide it, e.g. for screenshots)
if DEBUG and env.bool("DEBUG_TOOLBAR", default=True):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")


# Email Configuration
if DEBUG and not env("RESEND_API_KEY", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"

# All outgoing email goes through core/emails.py.
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="CivicDesk <noreply@usecivicdesk.com>")
EMAIL_REPLY_TO = env("EMAIL_REPLY_TO", default="")
# Absolute links in emails and background jobs (no request available there).
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")

# Inbound email: each building gets <token>@INBOUND_EMAIL_DOMAIN; Resend posts received mail to
# /anymail/resend/inbound/ (signature checked with RESEND_INBOUND_SECRET).
INBOUND_EMAIL_DOMAIN = env("INBOUND_EMAIL_DOMAIN", default="inbox.usecivicdesk.com")

ANYMAIL = {
    "RESEND_API_KEY": env("RESEND_API_KEY", default=""),
    "RESEND_INBOUND_SECRET": env("RESEND_INBOUND_SECRET", default=None),
}


# Production hardening (Render terminates HTTPS and forwards the original scheme).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # the platform's health check uses plain HTTP
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    # Start HSTS short; raise to 31536000 once HTTPS on the custom domain is confirmed working.
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
