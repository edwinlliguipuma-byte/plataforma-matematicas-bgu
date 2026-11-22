from django.urls import path
from . import views
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
    path("", views.aula_virtual, name="inicio_aula"),
    path("aula/", views.aula_virtual, name="aula_virtual"),
    path("docente/", panel_docente_institucional, name="panel_docente"),
    path("tarea/<int:tarea_id>/", views.subir_tarea, name="subir_tarea"),
    path("evaluacion/<int:evaluacion_id>/", views.ver_evaluacion, name="ver_evaluacion"),
    path("docente/crear-modulo-ia/", crear_modulo_ia, name="crear_modulo_ia"),
    path("modulo/<int:modulo_id>/", ver_modulo_interactivo, name="ver_modulo_interactivo"),
    path("api/estudiante/", api_buscar_estudiante, name="api_buscar_estudiante"),
    path(
        "api/modulo/<int:modulo_id>/calificar/",
        api_guardar_evaluacion_modulo,
        name="api_guardar_evaluacion_modulo",
    ),
    path("docente/esquelas/", centro_esquelas, name="centro_esquelas"),
    path(
        "docente/esquela/imprimir/<int:estudiante_id>/",
        imprimir_esquela,
        name="imprimir_esquela",
    ),
]

if hasattr(views, "registrar_nota_api"):
    urlpatterns.append(path("api/registrar-nota/", views.registrar_nota_api, name="registrar_nota_api"))