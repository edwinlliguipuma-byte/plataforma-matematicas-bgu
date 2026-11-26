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
)


def _normalizar_curso_bgu_post(request):
    if getattr(request, 'method', '') != 'POST':
        return
    raw = (request.POST.get('curso') or '').strip()
    if raw not in ('2DO BGU', '3ERO DE BGU', '2DO DE BGU'):
        return
    import re as _re
    pref = '2DO' if raw.startswith('2') else '3RO'
    esp = (request.POST.get('especialidad') or '').strip().lower()
    par = _re.sub(r'^paralelo\s+', '', (request.POST.get('paralelo') or '').strip().lower()).strip()
    cands = [
        c for c in CursoBGU.objects.all().order_by('id')
        if (_re.match(r'^(2do|2°|segundo)\b', (c.nombre or '').strip().lower()) if pref == '2DO'
            else _re.match(r'^(3ro|3ero|3°|tercero)\b', (c.nombre or '').strip().lower()))
    ]
    chosen = None
    for c in cands:
        cn = c.nombre.lower()
        par_ok = bool(par and _re.search(r'(?:^|[\s\'"])' + _re.escape(par) + r'(?:$|[\s\'"])', cn))
        if (esp and esp in cn) and par_ok:
            chosen = c
            break
    if not chosen and esp:
        for c in cands:
            if esp in c.nombre.lower():
                chosen = c
                break
    if not chosen and cands:
        chosen = cands[0]
    if chosen:
        mut = request.POST.copy()
        mut['curso'] = chosen.nombre
        request.POST = mut

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
    list_display = ("mostrar_nombre", "cedula", "curso", "telefono_representante")
    search_fields = (
        "apellidos_nombres",
        "cedula",
        "user__first_name",
        "user__last_name",
        "user__username",
    )
    list_filter = ("curso",)

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
    readonly_fields = ("enlace_directo",)

    def enlace_directo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero el módulo para generar su enlace."
        ruta = reverse("ver_evaluacion", args=[obj.pk])
        return _render_caja_enlace(ruta)

    enlace_directo.short_description = "Enlace directo para el estudiante"


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
    list_display = ("titulo", "curso", "especialidad", "paralelo", "asignatura", "fecha_creacion")
    list_filter = ("curso", "especialidad", "paralelo")
    search_fields = ("titulo", "asignatura")
    readonly_fields = ("enlace_modulo",)

    def enlace_modulo(self, obj):
        if not obj or not obj.pk:
            return "Guarda primero el módulo."
        ruta = reverse("ver_modulo_interactivo", args=[obj.pk])
        return _render_caja_enlace(ruta)

    enlace_modulo.short_description = "Enlace directo del Módulo Interactivo"


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
from .models import RegistroAsistencia, RegistroPizarra
admin.site.register(RegistroAsistencia)
admin.site.register(RegistroPizarra)