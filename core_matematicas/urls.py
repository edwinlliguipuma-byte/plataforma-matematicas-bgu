from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Redirige la página principal raíz (http://127.0.0.1:8000/) directamente al panel de administración
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    
    # Ruta del panel de administración
    path('admin/', admin.site.urls),
    
    # Si tienes rutas en tu app cursos, las incluimos aquí (puedes ajustar según tu estructura)
    path('', include('cursos.urls')),
]