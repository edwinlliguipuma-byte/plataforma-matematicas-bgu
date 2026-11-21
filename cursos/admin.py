from django.contrib import admin
from django.utils.html import format_html
from .models import (
    MuestraSelloFirma,
    CursoBGU,
    EstudiantePerfil,
    Tarea,
    EntregaTarea,
    Evaluacion,
    ResultadoEvaluacion,
)


@admin.register(MuestraSelloFirma)
class MuestraSelloFirmaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'vista_previa_sello', 'vista_previa_firma', 'activo', 'fecha_actualizacion')
    readonly_fields = ('vista_previa_sello', 'vista_previa_firma', 'fecha_actualizacion')

    def vista_previa_sello(self, obj):
        if obj.sello_base64:
            mime = obj.sello_mime or 'image/jpeg'
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:85px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.sello_base64
            )
        return "Sin imagen de sello"
    vista_previa_sello.short_description = "Vista Previa del Sello"

    def vista_previa_firma(self, obj):
        if obj.firma_base64:
            mime = obj.firma_mime or 'image/jpeg'
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:85px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.firma_base64
            )
        return "Sin imagen de firma"
    vista_previa_firma.short_description = "Vista Previa de la Firma"


@admin.register(CursoBGU)
class CursoBGUAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)


@admin.register(EstudiantePerfil)
class EstudiantePerfilAdmin(admin.ModelAdmin):
    list_display = ('apellidos_nombres', 'cedula', 'curso')
    search_fields = ('apellidos_nombres', 'cedula', 'user__first_name', 'user__last_name')
    list_filter = ('curso',)


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo_tarea', 'curso', 'total_sellos_esperados', 'fecha_limite')
    list_filter = ('tipo_tarea', 'curso')
    search_fields = ('titulo',)


@admin.register(EntregaTarea)
class EntregaTareaAdmin(admin.ModelAdmin):
    list_display = (
        'estudiante',
        'tarea',
        'nota_calculada',
        'estado_materia',
        'sellos_deberes',
        'sellos_talleres',
        'sellos_atrasados',
        'fecha_envio',
    )
    list_filter = ('tarea__tipo_tarea', 'estudiante__curso', 'tarea')
    search_fields = ('estudiante__apellidos_nombres', 'estudiante__cedula', 'tarea__titulo')
    readonly_fields = ('fecha_envio',)


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'curso', 'fecha_creacion')
    list_filter = ('curso',)
    search_fields = ('titulo',)


@admin.register(ResultadoEvaluacion)
class ResultadoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'evaluacion', 'nota_obtenida', 'fecha_registro')
    search_fields = ('estudiante__apellidos_nombres', 'estudiante__cedula')
    list_filter = ('estudiante__curso', 'evaluacion')