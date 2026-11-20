from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import CursoBGU, EstudiantePerfil, Tarea, EntregaTarea, Evaluacion, ResultadoEvaluacion


@admin.register(CursoBGU)
class CursoBGUAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(EstudiantePerfil)
class EstudiantePerfilAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo_admin', 'cedula', 'curso')
    search_fields = ('apellidos_nombres', 'user__first_name', 'user__last_name', 'cedula', 'curso__nombre')
    list_filter = ('curso',)

    @admin.display(description="Apellidos y Nombres")
    def nombre_completo_admin(self, obj):
        return obj.nombre_completo


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'curso', 'tipo_tarea', 'enlace_estudiante', 'fecha_limite')
    search_fields = ('titulo', 'curso__nombre')
    list_filter = ('curso', 'tipo_tarea')
    readonly_fields = ('enlace_estudiante_detalle',)
    fields = ('titulo', 'descripcion', 'curso', 'fecha_limite', 'tipo_tarea', 'enlace_estudiante_detalle')

    def get_queryset(self, request):
        self._request = request
        return super().get_queryset(request)

    def _url_tarea(self, obj):
        if not obj or not obj.pk:
            return ''
        path = reverse('subir_tarea', kwargs={'tarea_id': obj.pk})
        req = getattr(self, '_request', None)
        if req:
            return req.build_absolute_uri(path)
        return f"https://plataforma-matematicas-bgu.onrender.com{path}"

    @admin.display(description="URL del Estudiante")
    def enlace_estudiante(self, obj):
        url = self._url_tarea(obj)
        if not url:
            return "-"
        return format_html(
            '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
            '<a href="{}" target="_blank" style="padding:3px 8px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;">Abrir</a>'
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\').then(()=>{{this.innerText=\'¡Copiado!\';setTimeout(()=>this.innerText=\'Copiar link\',1500);}})" '
            'style="padding:3px 8px;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">Copiar link</button>'
            '</div>',
            url,
            url,
        )

    @admin.display(description="Enlace directo para el estudiante")
    def enlace_estudiante_detalle(self, obj):
        url = self._url_tarea(obj)
        if not url:
            return "Guarda primero para generar el enlace del estudiante."
        return format_html(
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
            '<input type="text" value="{}" readonly style="width:320px;padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;color:#0f172a;font-weight:600;">'
            '<a href="{}" target="_blank" style="padding:6px 12px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:700;">Abrir vista alumno</a>'
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\').then(()=>{{this.innerText=\'¡Copiado!\';setTimeout(()=>this.innerText=\'Copiar link\',1500);}})" '
            'style="padding:6px 12px;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:700;">Copiar link</button>'
            '</div>',
            url,
            url,
            url,
        )


@admin.register(EntregaTarea)
class EntregaTareaAdmin(admin.ModelAdmin):
    list_display = (
        'tarea',
        'estudiante',
        'estado_materia',
        'sellos_deberes',
        'sellos_talleres',
        'nota_calculada',
        'fecha_envio',
    )
    search_fields = ('estudiante__apellidos_nombres', 'estudiante__user__first_name', 'estudiante__user__last_name', 'estudiante__cedula', 'tarea__titulo')
    list_filter = ('estudiante__curso', 'tarea__tipo_tarea', 'tarea')


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'curso', 'enlace_estudiante', 'fecha_creacion')
    search_fields = ('titulo', 'curso__nombre')
    list_filter = ('curso',)
    readonly_fields = ('enlace_estudiante_detalle',)
    fields = ('titulo', 'descripcion', 'curso', 'enlace_estudiante_detalle')

    def get_queryset(self, request):
        self._request = request
        return super().get_queryset(request)

    def _url_evaluacion(self, obj):
        if not obj or not obj.pk:
            return ''
        path = reverse('ver_evaluacion', kwargs={'evaluacion_id': obj.pk})
        req = getattr(self, '_request', None)
        if req:
            return req.build_absolute_uri(path)
        return f"https://plataforma-matematicas-bgu.onrender.com{path}"

    @admin.display(description="URL del Estudiante")
    def enlace_estudiante(self, obj):
        url = self._url_evaluacion(obj)
        if not url:
            return "-"
        return format_html(
            '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
            '<a href="{}" target="_blank" style="padding:3px 8px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;">Abrir</a>'
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\').then(()=>{{this.innerText=\'¡Copiado!\';setTimeout(()=>this.innerText=\'Copiar link\',1500);}})" '
            'style="padding:3px 8px;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">Copiar link</button>'
            '</div>',
            url,
            url,
        )

    @admin.display(description="Enlace directo para el estudiante")
    def enlace_estudiante_detalle(self, obj):
        url = self._url_evaluacion(obj)
        if not url:
            return "Guarda la evaluación primero para generar el enlace del estudiante."
        return format_html(
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
            '<input type="text" value="{}" readonly style="width:320px;padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;color:#0f172a;font-weight:600;">'
            '<a href="{}" target="_blank" style="padding:6px 12px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:700;">Abrir vista alumno</a>'
            '<button type="button" onclick="navigator.clipboard.writeText(\'{}\').then(()=>{{this.innerText=\'¡Copiado!\';setTimeout(()=>this.innerText=\'Copiar link\',1500);}})" '
            'style="padding:6px 12px;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:700;">Copiar link</button>'
            '</div>',
            url,
            url,
            url,
        )


@admin.register(ResultadoEvaluacion)
class ResultadoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'evaluacion', 'nota_obtenida', 'fecha_registro')
    search_fields = ('estudiante__apellidos_nombres', 'estudiante__user__first_name', 'estudiante__user__last_name', 'estudiante__cedula', 'evaluacion__titulo')
    list_filter = ('estudiante__curso', 'evaluacion')