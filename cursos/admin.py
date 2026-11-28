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
        '<a href="{0}" target="_blank" style="background:#1d4ed8; color:#fff; padding:6px 12px; border-radius:6px; font-weight:bold; text-decoration:none; font-size:12px;">Abrir vista alumno</a>'
        '<button type="button" onclick="navigator.clipboard.writeText(window.location.origin + \'{0}\'); this.innerText=\'¡Copiado!\'; setTimeout(()=>this.innerText=\'Copiar link\', 2000);" '
        'style="background:#059669; color:#fff; border:none; padding:6px 12px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:12px;">Copiar link</button>'
        "</div>",
        ruta_relativa,
    )


def _badge_nota(valor):
    if valor is None:
        return "-"
    num = float(valor)
    if num >= 7.0:
        bg, color, border = "#dcfce7", "#166534", "#86efac"
    else:
        bg, color, border = "#fee2e2", "#991b1b", "#fca5a5"
    return format_html(
        '<span style="background:{}; color:{}; border:1px solid {}; padding:3px 10px; border-radius:999px; font-weight:800; font-size:12px; display:inline-block;">{}</span>',
        bg,
        color,
        border,
        f"{num:.2f}",
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
    show_full_result_count = False

    def vista_previa_sello(self, obj):
        if obj.sello_base64:
            mime = obj.sello_mime or "image/jpeg"
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:80px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.sello_base64,
            )
        return "Sin imagen de sello"

    vista_previa_sello.short_description = "Vista Previa del Sello"

    def vista_previa_firma(self, obj):
        if obj.firma_base64:
            mime = obj.firma_mime or "image/jpeg"
            return format_html(
                '<img src="data:{};base64,{}" style="max-height:80px; border-radius:8px; border:1px solid #cbd5e1;" />',
                mime,
                obj.firma_base64,
            )
        return "Sin imagen de firma"

    vista_previa_firma.short_description = "Vista Previa de la Firma"


@admin.register(CursoBGU)
class CursoBGUAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    show_full_result_count = False


@admin.register(EstudiantePerfil)
class EstudiantePerfilAdmin(admin.ModelAdmin):
    list_display = ("mostrar_nombre", "cedula", "curso", "retirado", "telefono_representante")
    list_editable = ("retirado",)
    list_select_related = ("user", "curso")
    list_per_page = 40
    show_full_result_count = False
    search_fields = (
        "apellidos_nombres",
        "cedula",
        "user__first_name",
        "user__last_name",
        "user__username",
    )
    list_filter = ("curso", "retirado")
    ordering = ("curso__nombre", "apellidos_nombres", "user__last_name")

    def mostrar_nombre(self, obj):
        return obj.nombre_completo

    mostrar_nombre.short_description = "Apellidos y Nombres"
    mostrar_nombre.admin_order_field = "apellidos_nombres"


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo_tarea", "curso", "total_sellos_esperados", "fecha_limite")
    list_select_related = ("curso",)
    list_per_page = 30
    show_full_result_count = False
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
        "curso_estudiante",
        "tarea",
        "badge_nota",
        "estado_materia",
        "sellos_deberes",
        "sellos_talleres",
        "sellos_atrasados",
        "fecha_envio",
    )
    list_select_related = ("estudiante", "estudiante__user", "estudiante__curso", "tarea")
    list_per_page = 35
    show_full_result_count = False
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

    def curso_estudiante(self, obj):
        return obj.estudiante.curso.nombre

    curso_estudiante.short_description = "Curso"

    def badge_nota(self, obj):
        return _badge_nota(obj.nota_calculada)

    badge_nota.short_description = "Calificación"
    badge_nota.admin_order_field = "nota_calculada"


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso", "fecha_creacion")
    list_select_related = ("curso",)
    list_per_page = 30
    show_full_result_count = False
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
    list_display = ("mostrar_estudiante", "curso_estudiante", "evaluacion", "badge_nota", "fecha_registro")
    list_select_related = ("estudiante", "estudiante__user", "estudiante__curso", "evaluacion")
    list_per_page = 35
    show_full_result_count = False
    search_fields = (
        "estudiante__apellidos_nombres",
        "estudiante__user__last_name",
        "estudiante__user__first_name",
        "estudiante__cedula",
        "evaluacion__titulo",
    )
    list_filter = ("estudiante__curso", "evaluacion")
    ordering = ("-fecha_registro",)

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"

    def curso_estudiante(self, obj):
        return obj.estudiante.curso.nombre

    curso_estudiante.short_description = "Curso"

    def badge_nota(self, obj):
        return _badge_nota(obj.nota_obtenida)

    badge_nota.short_description = "Nota obtenida"
    badge_nota.admin_order_field = "nota_obtenida"


@admin.register(ModuloInteractivo)
class ModuloInteractivoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso", "especialidad", "paralelo", "asignatura", "fecha_creacion")
    list_select_related = ("curso",)
    list_per_page = 30
    show_full_result_count = False
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
        "curso_estudiante",
        "motivo_principal",
        "plazo_entrega",
        "enviada_whatsapp",
        "fecha_emision",
    )
    list_select_related = ("estudiante", "estudiante__user", "estudiante__curso")
    list_per_page = 35
    show_full_result_count = False
    list_filter = ("enviada_whatsapp", "estudiante__curso")

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"

    def curso_estudiante(self, obj):
        return obj.estudiante.curso.nombre

    curso_estudiante.short_description = "Curso"


@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ("mostrar_estudiante", "curso_estudiante", "fecha", "badge_estado", "actualizado_en")
    list_select_related = ("estudiante", "estudiante__user", "estudiante__curso")
    list_per_page = 40
    show_full_result_count = False
    list_filter = ("estado", "estudiante__curso", "fecha")
    search_fields = ("estudiante__apellidos_nombres", "estudiante__cedula")
    ordering = ("-fecha", "estudiante__apellidos_nombres")

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"

    def curso_estudiante(self, obj):
        return obj.estudiante.curso.nombre

    curso_estudiante.short_description = "Curso"

    def badge_estado(self, obj):
        colores = {
            "P": ("#dcfce7", "#166534", "Presente (1.0)"),
            "J": ("#dbeafe", "#1e40af", "Justificado (0.9)"),
            "A": ("#fef3c7", "#92400e", "Atraso (0.7)"),
            "F": ("#fee2e2", "#991b1b", "Falta (0.0)"),
            "FG": ("#f3e8ff", "#6b21a8", "Fuga (0.0)"),
        }
        bg, fg, label = colores.get(obj.estado, ("#f1f5f9", "#334155", obj.estado))
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 10px; border-radius:999px; font-weight:700; font-size:12px;">{}</span>',
            bg,
            fg,
            label,
        )

    badge_estado.short_description = "Estado"


@admin.register(RegistroPizarra)
class RegistroPizarraAdmin(admin.ModelAdmin):
    list_display = ("mostrar_estudiante", "curso_estudiante", "fecha", "codigo_cuali", "badge_nota", "actualizado_en")
    list_select_related = ("estudiante", "estudiante__user", "estudiante__curso")
    list_per_page = 40
    show_full_result_count = False
    list_filter = ("estudiante__curso", "fecha")
    search_fields = ("estudiante__apellidos_nombres", "estudiante__cedula")
    ordering = ("-fecha", "estudiante__apellidos_nombres")

    def mostrar_estudiante(self, obj):
        return obj.estudiante.nombre_completo

    mostrar_estudiante.short_description = "Estudiante"

    def curso_estudiante(self, obj):
        return obj.estudiante.curso.nombre

    curso_estudiante.short_description = "Curso"

    def badge_nota(self, obj):
        return _badge_nota(obj.nota_cuanti)

    badge_nota.short_description = "Nota Pizarra"