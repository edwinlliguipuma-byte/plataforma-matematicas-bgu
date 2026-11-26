import csv
import json
import unicodedata
from datetime import datetime
from decimal import Decimal
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .models import CursoBGU, EstudiantePerfil, RegistroAsistencia, RegistroPizarra


def _clave_orden(est):
    txt = (est.nombre_completo or "").strip().upper()
    return "".join(
        c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
    )


@staff_member_required(login_url="/admin/login/")
def app_asistencia_offline(request):
    cursos = CursoBGU.objects.all().order_by("nombre")
    cursos_data = []
    for c in cursos:
        estudiantes = sorted(
            EstudiantePerfil.objects.filter(curso=c),
            key=_clave_orden,
        )
        cursos_data.append({
            "id": c.id,
            "nombre": c.nombre,
            "estudiantes": [
                {
                    "id": e.id,
                    "nombre": e.nombre_completo,
                    "cedula": e.cedula,
                }
                for e in estudiantes
            ],
        })

    return render(request, "cursos/asistencia_offline.html", {
        "cursos": cursos,
        "cursos_json": json.dumps(cursos_data, ensure_ascii=False),
    })


def service_worker_asistencia(request):
    sw_code = """
const CACHE_NAME = 'asistencia-bgu-v1';
const URLS_TO_CACHE = ['/docente/asistencia-offline/'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
"""
    return HttpResponse(sw_code, content_type="application/javascript")


@csrf_exempt
def api_sincronizar_asistencia(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        asistencias = data.get("asistencias", [])
        pizarras = data.get("pizarras", [])

        total_asist = 0
        total_piz = 0

        for item in asistencias:
            est_id = item.get("estudiante_id")
            fecha_str = item.get("fecha")
            estado = (item.get("estado") or "").strip().upper()
            if est_id and fecha_str and estado in ("P", "F", "A", "J"):
                fecha_obj = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                RegistroAsistencia.objects.update_or_create(
                    estudiante_id=int(est_id),
                    fecha=fecha_obj,
                    defaults={"estado": estado},
                )
                total_asist += 1

        equivalencias = {
            "EP": Decimal("10.00"),
            "BP": Decimal("8.50"),
            "DP": Decimal("6.50"),
            "NP": Decimal("4.00"),
        }

        for item in pizarras:
            est_id = item.get("estudiante_id")
            fecha_str = item.get("fecha")
            cuali = (item.get("codigo_cuali") or item.get("cuali") or "").strip().upper()
            if est_id and fecha_str and cuali in equivalencias:
                fecha_obj = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                nota_val = item.get("nota_cuanti")
                nota_dec = Decimal(str(nota_val)) if nota_val is not None else equivalencias[cuali]
                RegistroPizarra.objects.update_or_create(
                    estudiante_id=int(est_id),
                    fecha=fecha_obj,
                    defaults={
                        "codigo_cuali": cuali,
                        "nota_cuanti": nota_dec,
                    },
                )
                total_piz += 1

        return JsonResponse({
            "ok": True,
            "mensaje": f"Sincronizado correctamente: {total_asist} asistencias y {total_piz} notas de pizarra.",
        })
    except Exception as e:
        return JsonResponse({"ok": False, "mensaje": f"Error al sincronizar: {str(e)}"}, status=400)


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
                    celdas.append({
                        "nota": f"{val:.2f}".rstrip("0").rstrip("."),
                        "cuali": reg.codigo_cuali,
                    })
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