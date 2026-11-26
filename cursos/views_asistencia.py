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
        return JsonResponse({"ok": False, "mensaje": f"Error al sincronizar: {str(e)}"}, status=400)import csv
import unicodedata
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render
from .models import CursoBGU, EstudiantePerfil, RegistroAsistencia, RegistroPizarra


def _clave_orden(est):
    txt = (est.nombre_completo or "").strip().upper()
    return "".join(
        c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
    )


@staff_member_required(login_url="/admin/login/")
def sabana_asistencia_pizarra(request):
    cursos = CursoBGU.objects.all().order_by("nombre")
    curso_id = request.GET.get("curso", "").strip()

    curso_actual = None
    if curso_id.isdigit():
        curso_actual = cursos.filter(id=int(curso_id)).first()
    if not curso_actual and cursos.exists():
        curso_actual = cursos.first()

    fechas_asistencia = []
    fechas_pizarra = []
    filas_asistencia = []
    filas_pizarra = []

    if curso_actual:
        estudiantes = sorted(
            EstudiantePerfil.objects.filter(curso=curso_actual),
            key=_clave_orden,
        )

        # 1. ASISTENCIA HORIZONTAL
        fechas_asistencia = list(
            RegistroAsistencia.objects.filter(estudiante__curso=curso_actual)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        asist_qs = RegistroAsistencia.objects.filter(estudiante__curso=curso_actual)
        mapa_asist = {(a.estudiante_id, a.fecha): a.estado for a in asist_qs}

        for idx, est in enumerate(estudiantes, start=1):
            celdas = []
            marcadas = 0
            asistidas = 0
            for f in fechas_asistencia:
                est_val = mapa_asist.get((est.id, f), "-")
                celdas.append(est_val)
                if est_val in ("P", "A", "J", "F"):
                    marcadas += 1
                    if est_val in ("P", "A", "J"):
                        asistidas += 1
            porcentaje = round((asistidas / marcadas) * 100, 1) if marcadas > 0 else 0.0
            filas_asistencia.append({
                "num": idx,
                "estudiante": est,
                "celdas": celdas,
                "porcentaje": porcentaje,
            })

        # 2. PIZARRA HORIZONTAL
        fechas_pizarra = list(
            RegistroPizarra.objects.filter(estudiante__curso=curso_actual)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        piz_qs = RegistroPizarra.objects.filter(estudiante__curso=curso_actual)
        mapa_piz = {(p.estudiante_id, p.fecha): p for p in piz_qs}

        for idx, est in enumerate(estudiantes, start=1):
            celdas = []
            notas = []
            for f in fechas_pizarra:
                reg = mapa_piz.get((est.id, f))
                if reg:
                    val = float(reg.nota_cuanti)
                    notas.append(val)
                    celdas.append({"nota": f"{val:.2f}".rstrip("0").rstrip("."), "cuali": reg.codigo_cuali})
                else:
                    celdas.append(None)
            promedio = round(sum(notas) / len(notas), 2) if notas else 0.0
            filas_pizarra.append({
                "num": idx,
                "estudiante": est,
                "celdas": celdas,
                "promedio": f"{promedio:.2f}",
            })

    return render(request, "cursos/sabana_asistencia.html", {
        "cursos": cursos,
        "curso_actual": curso_actual,
        "fechas_asistencia": fechas_asistencia,
        "filas_asistencia": filas_asistencia,
        "fechas_pizarra": fechas_pizarra,
        "filas_pizarra": filas_pizarra,
    })


@staff_member_required(login_url="/admin/login/")
def exportar_sabana_csv(request):
    curso_id = request.GET.get("curso", "").strip()
    tipo = request.GET.get("tipo", "asistencia").strip()
    curso = CursoBGU.objects.filter(id=int(curso_id)).first() if curso_id.isdigit() else None

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    nombre_curso = curso.nombre.replace(" ", "_").replace('"', "") if curso else "Curso"
    response["Content-Disposition"] = f'attachment; filename="III_Trimestre_{tipo.upper()}_{nombre_curso}.csv"'

    writer = csv.writer(response, delimiter=";")
    if not curso:
        return response

    estudiantes = sorted(EstudiantePerfil.objects.filter(curso=curso), key=_clave_orden)

    if tipo == "pizarra":
        fechas = list(
            RegistroPizarra.objects.filter(estudiante__curso=curso)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        mapa = {(p.estudiante_id, p.fecha): float(p.nota_cuanti) for p in RegistroPizarra.objects.filter(estudiante__curso=curso)}
        encabezado = ["N°", "Apellidos y Nombres", "Cédula"] + [f.strftime("%d/%m/%Y") for f in fechas] + ["Promedio Pizarra"]
        writer.writerow(encabezado)

        for idx, est in enumerate(estudiantes, start=1):
            fila = [idx, est.nombre_completo, est.cedula]
            notas = []
            for f in fechas:
                if (est.id, f) in mapa:
                    n = mapa[(est.id, f)]
                    notas.append(n)
                    fila.append(f"{n:.2f}".replace(".", ","))
                else:
                    fila.append("-")
            prom = round(sum(notas) / len(notas), 2) if notas else 0.0
            fila.append(f"{prom:.2f}".replace(".", ","))
            writer.writerow(fila)
    else:
        fechas = list(
            RegistroAsistencia.objects.filter(estudiante__curso=curso)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        mapa = {(a.estudiante_id, a.fecha): a.estado for a in RegistroAsistencia.objects.filter(estudiante__curso=curso)}
        encabezado = ["N°", "Apellidos y Nombres", "Cédula"] + [f.strftime("%d/%m/%Y") for f in fechas] + ["% Asistencia"]
        writer.writerow(encabezado)

        for idx, est in enumerate(estudiantes, start=1):
            fila = [idx, est.nombre_completo, est.cedula]
            marcadas = 0
            asistidas = 0
            for f in fechas:
                val = mapa.get((est.id, f), "-")
                fila.append(val)
                if val in ("P", "A", "J", "F"):
                    marcadas += 1
                    if val in ("P", "A", "J"):
                        asistidas += 1
            pct = round((asistidas / marcadas) * 100, 1) if marcadas > 0 else 0.0
            fila.append(f"{pct}%".replace(".", ","))
            writer.writerow(fila)

    return response