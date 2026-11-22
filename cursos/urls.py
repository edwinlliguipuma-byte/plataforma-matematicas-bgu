from django.urls import path
from cursos import views

urlpatterns = [
    path('api/estudiante/<str:cedula>/', views.buscar_estudiante_json, name='buscar_estudiante_json'),
    path('api/evaluacion/guardar-nota/', views.api_guardar_nota_evaluacion, name='api_guardar_nota_evaluacion'),
    path('tarea/<int:tarea_id>/subir/', views.subir_tarea, name='subir_tarea'),
    path('evaluacion/<int:evaluacion_id>/', views.ver_evaluacion, name='ver_evaluacion'),
    path('aula/', views.portal_estudiante, name='portal_estudiante'),
    path('docente/', views.panel_docente, name='panel_docente'),
    path('docente/exportar/', views.exportar_notas_csv, name='exportar_notas_csv'),
]

from django.urls import path
from .modulo_ia import (
    panel_docente_institucional,
    crear_modulo_ia,
    ver_modulo_interactivo,
    api_buscar_estudiante,
    api_guardar_evaluacion_modulo,
    centro_esquelas,
    imprimir_esquela,
)

urlpatterns = [
    path('docente/', panel_docente_institucional, name='panel_docente'),
    path('docente/crear-modulo-ia/', crear_modulo_ia, name='crear_modulo_ia'),
    path('modulo/<int:modulo_id>/', ver_modulo_interactivo, name='ver_modulo_interactivo'),
    path('api/estudiante/', api_buscar_estudiante, name='api_buscar_estudiante'),
    path('api/modulo/<int:modulo_id>/calificar/', api_guardar_evaluacion_modulo, name='api_guardar_evaluacion_modulo'),
    path('docente/esquelas/', centro_esquelas, name='centro_esquelas'),
    path('docente/esquela/imprimir/<int:estudiante_id>/', imprimir_esquela, name='imprimir_esquela'),
] + urlpatterns
