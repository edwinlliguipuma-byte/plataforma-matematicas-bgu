import json
from datetime import datetime
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from .models import CursoBGU, EstudiantePerfil, RegistroAsistencia, RegistroPizarra


@staff_member_required
def app_asistencia_offline(request):
    """Entrega la app móvil con todos los cursos y estudiantes reales de la BD."""
    cursos_data = []
    for curso in CursoBGU.objects.all().order_by("nombre"):
        estudiantes = EstudiantePerfil.objects.filter(curso=curso).order_by("apellidos_nombres", "cedula")
        cursos_data.append({
            "id": curso.id,
            "nombre": curso.nombre,
            "estudiantes": [
                {
                    "num": idx + 1,
                    "id": est.id,
                    "cedula": est.cedula,
                    "name": est.nombre_completo,
                }
                for idx, est in enumerate(estudiantes)
            ],
        })

    return render(request, "cursos/asistencia_offline.html", {
        "cursos_json": json.dumps(cursos_data, ensure_ascii=False),
    })


def service_worker_asistencia(request):
    """Permite que el navegador del celular abra la app sin internet."""
    sw_code = """
    const CACHE_NAME = 'asistencia-noboa-v1';
    const URLS_TO_CACHE = ['/docente/asistencia-offline/'];

    self.addEventListener('install', event => {
      event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
      );
      self.skipWaiting();
    });

    self.addEventListener('fetch', event => {
      if (event.request.method !== 'GET') return;
      event.respondWith(
        fetch(event.request)
          .then(response => {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
            return response;
          })
          .catch(() => caches.match(event.request))
      );
    });
    """
    return HttpResponse(sw_code, content_type="application/javascript")


@csrf_exempt
def api_sincronizar_asistencia(request):
    """Recibe el JSON desde el celular cuando llega a casa y guarda en la base de datos."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        cursos_payload = payload.get("cursos", {})
        guardados_asist = 0
        guardados_piz = 0

        for curso_id_str, datos_curso in cursos_payload.items():
            scale = datos_curso.get("scale", {"EP": 10.0, "BP": 8.5, "DP": 6.5, "NP": 4.0})
            records = datos_curso.get("records", {})
            board_records = datos_curso.get("boardRecords", {})

            estudiantes_map = {
                e.cedula: e for e in EstudiantePerfil.objects.filter(curso_id=int(curso_id_str))
            }

            # 1. Guardar Asistencias
            for fecha_str, marcas in records.items():
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                for cedula, estado in marcas.items():
                    est = estudiantes_map.get(cedula)
                    if not est:
                        continue
                    if estado in ("P", "F", "A", "J"):
                        RegistroAsistencia.objects.update_or_create(
                            estudiante=est,
                            fecha=fecha_obj,
                            defaults={"estado": estado},
                        )
                        guardados_asist += 1
                    elif estado == "":
                        RegistroAsistencia.objects.filter(estudiante=est, fecha=fecha_obj).delete()

            # 2. Guardar Notas de Pizarra / Lección
            for fecha_str, marcas_b in board_records.items():
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                for cedula, b_code in marcas_b.items():
                    est = estudiantes_map.get(cedula)
                    if not est:
                        continue
                    if b_code in ("EP", "BP", "DP", "NP"):
                        nota_val = float(scale.get(b_code, 0))
                        RegistroPizarra.objects.update_or_create(
                            estudiante=est,
                            fecha=fecha_obj,
                            defaults={"codigo_cuali": b_code, "nota_cuanti": nota_val},
                        )
                        guardados_piz += 1
                    elif b_code == "":
                        RegistroPizarra.objects.filter(estudiante=est, fecha=fecha_obj).delete()

        return JsonResponse({
            "ok": True,
            "mensaje": f"Sincronizado: {guardados_asist} asistencias y {guardados_piz} notas de pizarra.",
        })
    except Exception as e:
        return JsonResponse({"ok": False, "mensaje": f"Error al sincronizar: {str(e)}"}, status=400)