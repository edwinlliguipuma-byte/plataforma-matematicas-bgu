from django.urls import path
from cursos import views
from .modulo_ia import (
    panel_docente_institucional,
    crear_modulo_ia,
    ver_modulo_interactivo,
    api_buscar_estudiante,
    api_guardar_evaluacion_modulo,
    centro_esquelas,
    imprimir_esquela,
)
from .views_asistencia import (
    app_asistencia_offline,
    service_worker_asistencia,
    api_sincronizar_asistencia,
    sabana_asistencia_pizarra,
    exportar_sabana_csv,
)
from .views_excel import exportar_plantilla_xlsm

urlpatterns = [
    path('docente/', panel_docente_institucional, name='panel_docente'),
    path('docente/exportar-xlsm/', exportar_plantilla_xlsm, name='exportar_plantilla_xlsm'),
    path('docente/crear-modulo-ia/', crear_modulo_ia, name='crear_modulo_ia'),
    path('modulo/<int:modulo_id>/', ver_modulo_interactivo, name='ver_modulo_interactivo'),
    path('api/estudiante/', api_buscar_estudiante, name='api_buscar_estudiante'),
    path('api/modulo/<int:modulo_id>/calificar/', api_guardar_evaluacion_modulo, name='api_guardar_evaluacion_modulo'),
    path('docente/esquelas/', centro_esquelas, name='centro_esquelas'),
    path('docente/esquela/imprimir/<int:estudiante_id>/', imprimir_esquela, name='imprimir_esquela'),
    path('docente/asistencia-offline/', app_asistencia_offline, name='app_asistencia_offline'),
    path('sw-asistencia.js', service_worker_asistencia, name='sw_asistencia'),
    path('api/sincronizar-asistencia/', api_sincronizar_asistencia, name='api_sincronizar_asistencia'),
    path('docente/sabana-asistencia/', sabana_asistencia_pizarra, name='sabana_asistencia_pizarra'),
    path('docente/exportar-sabana/', exportar_sabana_csv, name='exportar_sabana_csv'),
    path('api/estudiante/<str:cedula>/', views.buscar_estudiante_json, name='buscar_estudiante_json'),
    path('api/evaluacion/guardar-nota/', views.api_guardar_nota_evaluacion, name='api_guardar_nota_evaluacion'),
    path('tarea/<int:tarea_id>/subir/', views.subir_tarea, name='subir_tarea'),
    path('evaluacion/<int:evaluacion_id>/', views.ver_evaluacion, name='ver_evaluacion'),
    path('aula/', views.portal_estudiante, name='portal_estudiante'),
    path('docente/exportar/', views.exportar_notas_csv, name='exportar_notas_csv'),
]