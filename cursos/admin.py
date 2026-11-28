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
    ModuloInteractivo,
    EsquelaIncumplimiento,
    RegistroAsistencia,
    RegistroPizarra,
)


def _render_caja_enlace(ruta_relativa):
    return format_html(
        '<div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">'
        '<input type="text" readonly value="{0}" '
        'style="width:320px; max-width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; font-family:monospace; font-size:12px;" '
        'onfocus="this.select();" />'
        '<a href="{0}" target="_blank" style="background:#2563eb; color:#fff; padding:6px 12px; border-radius:6px; font-weight:bold; text-decoration:none; font-size:12px;">Abrir vista alumno</a>'
        '<button type="button" onclick="navigator.clipboard.writeText(window.location.origin + \'{0}\'); this.innerText=\'¡Copiado!\'; setTimeout(()=>this.innerText=\'Copiar link\', 2000);" '
        'style="background:#16a34a; color:#fff; border:none; padding:6px 12px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:12px;">Copiar link</button>'
        "</div>",
        ruta_relativa,
    )


@admin.register(MuestraSelloFirma)
class MuestraSelloFirmaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "vista_previa_sello",
        "vista_previa_firma",
        "activo",
        "fecha_actualizacion",
    )
    readonly_fields = ("vista_previa_sello", "vista_previa_firma", "fecha_actualizacion")
    exclude = ("sello_base64", "sello_mime", "firma_base64", "firma_mime")

    def vista_previa_sello(self, obj):
        if obj.sello_base64:
            mime = obj.sello_mime or "image/jpeg"
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:90px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.sello_base64,
            )
        return "Sin imagen de sello"

    vista_previa_sello.short_description = "Vista Previa del Sello"

    def vista_previa_firma(self, obj):
        if obj.firma_base64:
            mime = obj.firma_mime or "image/jpeg"
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:90px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.firma_base64,
            )
        return "Sin imagen de firma"

    vista_previa_firma.short_description = "Vista Previa de la Firma"


@admin.register(CursoBGU)
class CursoBGUAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)


@admin.register(EstudiantePerfil)
class EstudiantePerfilAdmin(admin.ModelAdmin):
    list_display = ("mostrar_nombre", "cedula", "curso", "retirado", "telefono_representante")
    search_fields = (
        "apellidos_nombres",
        "cedula",
        "user__first_name",
        "user__last_name",
        "user__username",
    )
    list_filter = ("curso", "retirado")

    def mostrar_nombre(self, obj):
        return obj.nombre_completo

    mostrar_nombre.short_description = "Apellidos y Nombres"
    mostrar_nombre.admin_order_field = "user__last_name"


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo_tarea", "curso", "total_sellos_esperados", "fecha_limite")
    list_filter = ("tipo_tarea", "curso")
    search_fields = ("titulo",)
    readonly_fields = ("enlace_directo",)

    def enlace_directo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero la tarea para generar su enlace."
        ruta = reverse("subir_tarea", args=[obj.pk])
        return _render_caja_enlace(ruta)

    enlace_directo.short_description = "Enlace directo para el estudiante"


@admin.register(EntregaTarea)
class EntregaTareaAdmin(admin.ModelAdmin):
    list_display = (
        "mostrar_estudiante",
        "tarea",
        "nota_calculada",
        "estado_materia",
        "sellos_deberes",
        "sellos_talleres",
        "sellos_atrasados",
        "fecha_envio",
    )
    list_filter = ("tarea__tipo_tarea", "estudiante__curso", "tarea")
    search_fields = (
        "estudiante__apellidos_nombres",
        "estudiante__user__last_name",
        "estudiante__user__first_name",
        "estudiante__cedula",
        "tarea__titulo",
    )
    readonly_fields = ("fecha_envio",)

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso", "fecha_creacion")
    list_filter = ("curso",)
    search_fields = ("titulo",)


@admin.register(ResultadoEvaluacion)
class ResultadoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ("mostrar_estudiante", "evaluacion", "nota_obtenida", "fecha_registro")
    search_fields = (
        "estudiante__apellidos_nombres",
        "estudiante__user__last_name",
        "estudiante__user__first_name",
        "estudiante__cedula",
    )
    list_filter = ("estudiante__curso", "evaluacion")

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"


@admin.register(ModuloInteractivo)
class ModuloInteractivoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo_columna_sabana", "curso", "especialidad", "paralelo", "fecha_creacion")
    list_filter = ("curso", "especialidad", "paralelo")
    search_fields = ("titulo", "asignatura")
    readonly_fields = ("enlace_modulo", "evaluacion_vinculada")

    def tipo_columna_sabana(self, obj):
        tit = (obj.evaluacion_vinculada.titulo if obj.evaluacion_vinculada else obj.titulo or "").upper()
        if tit.startswith("[EIS]") or tit.startswith("[MÓDULO IA]") or tit.startswith("[MODULO IA]") or "(EIS)" in tit:
            return "🧬 EIS (Trimestral)"
        return "📝 Evaluación Online"

    tipo_columna_sabana.short_description = "Columna en Sábana"

    def enlace_modulo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero el módulo."
        ruta = reverse("ver_modulo_interactivo", args=[obj.pk])
        return _render_caja_enlace(ruta)

    enlace_modulo.short_description = "Enlace directo del Módulo Interactivo"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.evaluacion_vinculada:
            tit_actual = (obj.evaluacion_vinculada.titulo or "").strip()
            es_eis = (
                tit_actual.upper().startswith("[EIS]")
                or tit_actual.upper().startswith("[MÓDULO IA]")
                or tit_actual.upper().startswith("[MODULO IA]")
                or "(EIS)" in tit_actual.upper()
            )
            prefijo = "[EIS]" if es_eis else "[Evaluación IA]"
            obj.evaluacion_vinculada.titulo = f"{prefijo} {obj.titulo}"
            obj.evaluacion_vinculada.curso = obj.curso
            obj.evaluacion_vinculada.save(update_fields=["titulo", "curso"])


@admin.register(EsquelaIncumplimiento)
class EsquelaIncumplimientoAdmin(admin.ModelAdmin):
    list_display = (
        "mostrar_estudiante",
        "motivo_principal",
        "plazo_entrega",
        "enviada_whatsapp",
        "fecha_emision",
    )
    list_filter = ("enviada_whatsapp", "estudiante__curso")

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"


admin.site.register(RegistroAsistencia)
admin.site.register(RegistroPizarra)
