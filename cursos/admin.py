from django.contrib import admin
from django.urls import reverse
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


def _render_caja_enlace(ruta_relativa):
    return format_html(
        '<div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">'
        '<input type="text" readonly value="{0}" id="inp-link-{1}" '
        'style="width:320px; max-width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; font-family:monospace; font-size:12px;" '
        'onfocus="this.select();" />'
        '<a href="{0}" target="_blank" style="background:#2563eb; color:#fff; padding:6px 12px; border-radius:6px; font-weight:bold; text-decoration:none; font-size:12px;">Abrir vista alumno</a>'
        '<button type="button" onclick="navigator.clipboard.writeText(window.location.origin + \'{0}\'); this.innerText=\'¡Copiado!\'; setTimeout(()=>this.innerText=\'Copiar link\', 2000);" '
        'style="background:#16a34a; color:#fff; border:none; padding:6px 12px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:12px;">Copiar link</button>'
        '</div>',
        ruta_relativa,
        abs(hash(ruta_relativa)),
    )


@admin.register(MuestraSelloFirma)
class MuestraSelloFirmaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'vista_previa_sello', 'vista_previa_firma', 'activo', 'fecha_actualizacion')
    readonly_fields = ('vista_previa_sello', 'vista_previa_firma', 'fecha_actualizacion')

    def vista_previa_sello(self, obj):
        if obj.sello_base64:
            mime = obj.sello_mime or 'image/jpeg'
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:90px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.sello_base64,
            )
        return "Sin imagen de sello"
    vista_previa_sello.short_description = "Vista Previa del Sello"

    def vista_previa_firma(self, obj):
        if obj.firma_base64:
            mime = obj.firma_mime or 'image/jpeg'
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:90px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.firma_base64,
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
    readonly_fields = ('enlace_directo',)

    def enlace_directo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero la tarea para generar su enlace."
        ruta = reverse('subir_tarea', args=[obj.pk])
        return _render_caja_enlace(ruta)
    enlace_directo.short_description = "Enlace directo para el estudiante"


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
    readonly_fields = ('enlace_directo',)

    def enlace_directo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero el módulo para generar su enlace."
        ruta = reverse('ver_evaluacion', args=[obj.pk])
        return _render_caja_enlace(ruta)
    enlace_directo.short_description = "Enlace directo para el estudiante"


@admin.register(ResultadoEvaluacion)
class ResultadoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'evaluacion', 'nota_obtenida', 'fecha_registro')
    search_fields = ('estudiante__apellidos_nombres', 'estudiante__cedula')
    list_filter = ('estudiante__curso', 'evaluacion')