from django.urls import path
from cursos import views

urlpatterns = [
    path('api/estudiante/<str:cedula>/', views.buscar_estudiante_json, name='buscar_estudiante_json'),
    path('tarea/<int:tarea_id>/subir/', views.subir_tarea, name='subir_tarea'),
    path('evaluacion/<int:evaluacion_id>/', views.ver_evaluacion, name='ver_evaluacion'),
]