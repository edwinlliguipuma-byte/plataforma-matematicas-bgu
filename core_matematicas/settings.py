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
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CONFIGURACIÓN VISUAL DE JAZZMIN (DISEÑO MODERNO Y GRANDE) ---
JAZZMIN_SETTINGS = {
    "site_title": "Matemáticas BGU Técnico",
    "site_header": "Matemáticas BGU Técnico",
    "site_brand": "Matemáticas BGU Técnico",
    "welcome_sign": "Bienvenido al Sistema Académico • U.E. Dr. Enrique Noboa",
    "copyright": "Colegio BGU Técnico",
    "search_model": ["cursos.EstudiantePerfil"],

    # Botones en la barra blanca superior (junto al buscador)
    "topmenu_links": [
        {"name": "Inicio", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "📊 Panel Docente (Notas y Excel)", "url": "/docente/", "new_window": False},
        {"name": "🎓 Aula Virtual Estudiantes", "url": "/aula/", "new_window": True},
    ],

    # Enlaces directos en el menú lateral oscuro dentro de "Cursos"
    "custom_links": {
        "cursos": [
            {
                "name": "📊 Abrir Panel Docente (Excel)",
                "url": "/docente/",
                "icon": "fas fa-chart-line",
            },
            {
                "name": "🎓 Ver Aula Virtual (/aula/)",
                "url": "/aula/",
                "icon": "fas fa-graduation-cap",
                "new_window": True,
            },
        ]
    },

    # Íconos profesionales para cada sección
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
    },

    "show_sidebar": True,
    "navigation_expanded": True,
    "changeform_format": "horizontal_tabs",
}