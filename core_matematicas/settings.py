import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-@core-matematicas-bgu-tecnico-key'
)

DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)

# Aplicaciones instaladas (Jazzmin debe ir ANTES de 'django.contrib.admin')
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'cursos',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core_matematicas.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core_matematicas.wsgi.application'

if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'es-ec'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_MAX_AGE = 31536000  # Caché de 1 año en navegador para que las pestañas abran al instante
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CONFIGURACIÓN VISUAL DE JAZZMIN (DISEÑO EJECUTIVO PANTALLA COMPLETA) ---
JAZZMIN_SETTINGS = {
    "site_title": "U.E. Dr. Enrique Noboa • Msc. Edwin Lliguipuma",
    "site_header": "U.E. Dr. Enrique Noboa",
    "site_brand": "U.E. Dr. Enrique Noboa",
    "welcome_sign": "Plataforma Académica BGU • Creado por Msc. Edwin Lliguipuma — U.E. Dr. Enrique Noboa",
    "copyright": "Msc. Edwin Lliguipuma • Unidad Educativa Dr. Enrique Noboa",
    "search_model": ["cursos.EstudiantePerfil"],
    "custom_css": "cursos/css/admin_pro.css",

    # Accesos directos en la barra superior
    "topmenu_links": [
        {"name": "📊 Panel Docente (Notas)", "url": "/docente/", "new_window": False},
        {"name": "✨ Crear Módulo IA", "url": "/docente/crear-modulo-ia/", "new_window": False},
        {"name": "📱 Asistencia Offline", "url": "/docente/asistencia-offline/", "new_window": False},
        {"name": "📋 Sábana Trimestral", "url": "/docente/sabana-asistencia/", "new_window": False},
        {"name": "🎓 Aula Virtual", "url": "/aula/", "new_window": True},
    ],

    # Enlaces directos en el menú lateral dentro de "Cursos"
    "custom_links": {
        "cursos": [
            {
                "name": "📊 Panel Docente (Notas y Excel)",
                "url": "/docente/",
                "icon": "fas fa-chart-line",
            },
            {
                "name": "✨ Crear Módulo IA (EIS)",
                "url": "/docente/crear-modulo-ia/",
                "icon": "fas fa-magic",
            },
            {
                "name": "📱 App Asistencia y Pizarra",
                "url": "/docente/asistencia-offline/",
                "icon": "fas fa-mobile-alt",
            },
            {
                "name": "📋 Sábana Asistencia y Pizarra",
                "url": "/docente/sabana-asistencia/",
                "icon": "fas fa-table",
            },
            {
                "name": "📨 Centro de Esquelas",
                "url": "/docente/esquelas/",
                "icon": "fas fa-envelope-open-text",
            },
            {
                "name": "🎓 Aula Virtual Estudiantes",
                "url": "/aula/",
                "icon": "fas fa-graduation-cap",
                "new_window": True,
            },
        ]
    },

    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "cursos.CursoBGU": "fas fa-chalkboard",
        "cursos.EstudiantePerfil": "fas fa-user-graduate",
        "cursos.Evaluacion": "fas fa-book-open",
        "cursos.ResultadoEvaluacion": "fas fa-check-circle",
        "cursos.Tarea": "fas fa-file-alt",
        "cursos.EntregaTarea": "fas fa-clipboard-check",
        "cursos.ModuloInteractivo": "fas fa-robot",
        "cursos.EsquelaIncumplimiento": "fas fa-file-invoice",
        "cursos.MuestraSelloFirma": "fas fa-stamp",
        "cursos.RegistroAsistencia": "fas fa-user-check",
        "cursos.RegistroPizarra": "fas fa-chalkboard-teacher",
    },

    "show_sidebar": True,
    "navigation_expanded": True,
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-navy",
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": True,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": True,
    "theme": "default",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}