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
const CACHE_NAME = 'asistencia-bgu-v5';
const URLS_TO_CACHE = ['/docente/asistencia-offline/'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
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

        mapa_codigo_interno = {
            10: "EP",
            8: "BP",
            6: "DP",
            4: "NP",
        }

        for item in pizarras:
            est_id = item.get("estudiante_id")
            fecha_str = item.get("fecha")
            nota_raw = item.get("nota_cuanti")
            if est_id and fecha_str and nota_raw is not None:
                nota_num = float(nota_raw)
                nota_int = int(round(nota_num))
                if nota_int in mapa_codigo_interno:
                    fecha_obj = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                    RegistroPizarra.objects.update_or_create(
                        estudiante_id=int(est_id),
                        fecha=fecha_obj,
                        defaults={
                            "codigo_cuali": mapa_codigo_interno[nota_int],
                            "nota_cuanti": Decimal(f"{nota_num:.2f}"),
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
    promedio_general_asistencia = 0.0
    promedio_general_pizarra = 0.0

    if curso_actual:
        estudiantes = sorted(
            EstudiantePerfil.objects.filter(curso=curso_actual),
            key=_clave_orden,
        )

        # 1. TABLA HORIZONTAL DE ASISTENCIA + PORCENTAJE TRIMESTRAL
        fechas_asistencia = list(
            RegistroAsistencia.objects.filter(estudiante__curso=curso_actual)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        asist_qs = RegistroAsistencia.objects.filter(estudiante__curso=curso_actual)
        mapa_asist = {(a.estudiante_id, a.fecha): a.estado for a in asist_qs}

        porcentajes_curso = []
        for idx, est in enumerate(estudiantes, start=1):
            celdas = []
            cnt_p = cnt_f = cnt_a = cnt_j = 0
            for f in fechas_asistencia:
                est_val = mapa_asist.get((est.id, f), "-")
                celdas.append(est_val)
                if est_val == "P":
                    cnt_p += 1
                elif est_val == "F":
                    cnt_f += 1
                elif est_val == "A":
                    cnt_a += 1
                elif est_val == "J":
                    cnt_j += 1

            marcadas = cnt_p + cnt_f + cnt_a + cnt_j
            asistidas = cnt_p + cnt_a + cnt_j
            porcentaje = round((asistidas / marcadas) * 100, 1) if marcadas > 0 else 0.0
            if marcadas > 0:
                porcentajes_curso.append(porcentaje)

            filas_asistencia.append({
                "num": idx,
                "estudiante": est,
                "celdas": celdas,
                "cnt_p": cnt_p,
                "cnt_f": cnt_f,
                "cnt_a": cnt_a,
                "cnt_j": cnt_j,
                "marcadas": marcadas,
                "porcentaje": porcentaje,
            })

        if porcentajes_curso:
            promedio_general_asistencia = round(sum(porcentajes_curso) / len(porcentajes_curso), 1)

        # 2. TABLA HORIZONTAL DE PIZARRA + PROMEDIO TRIMESTRAL
        fechas_pizarra = list(
            RegistroPizarra.objects.filter(estudiante__curso=curso_actual)
            .values_list("fecha", flat=True)
            .distinct()
            .order_by("fecha")
        )
        piz_qs = RegistroPizarra.objects.filter(estudiante__curso=curso_actual)
        mapa_piz = {(p.estudiante_id, p.fecha): p for p in piz_qs}

        promedios_curso = []
        for idx, est in enumerate(estudiantes, start=1):
            celdas = []
            notas = []
            for f in fechas_pizarra:
                reg = mapa_piz.get((est.id, f))
                if reg:
                    val = float(reg.nota_cuanti)
                    notas.append(val)
                    celdas.append(f"{val:.2f}".rstrip("0").rstrip("."))
                else:
                    celdas.append(None)

            tiene_notas = len(notas) > 0
            promedio = round(sum(notas) / len(notas), 2) if tiene_notas else 0.0
            if tiene_notas:
                promedios_curso.append(promedio)

            filas_pizarra.append({
                "num": idx,
                "estudiante": est,
                "celdas": celdas,
                "cantidad_notas": len(notas),
                "tiene_notas": tiene_notas,
                "promedio": f"{promedio:.2f}" if tiene_notas else "-",
                "promedio_num": promedio,
            })

        if promedios_curso:
            promedio_general_pizarra = round(sum(promedios_curso) / len(promedios_curso), 2)

    return render(request, "cursos/sabana_asistencia.html", {
        "cursos": cursos,
        "curso_actual": curso_actual,
        "fechas_asistencia": fechas_asistencia,
        "filas_asistencia": filas_asistencia,
        "fechas_pizarra": fechas_pizarra,
        "filas_pizarra": filas_pizarra,
        "promedio_general_asistencia": promedio_general_asistencia,
        "promedio_general_pizarra": f"{promedio_general_pizarra:.2f}",
    })


@staff_member_required(login_url="/admin/login/")
def exportar_sabana_csv(request):
    curso_id = request.GET.get("curso", "").strip()
    tipo = request.GET.get("tipo", "consolidado").strip()
    curso = CursoBGU.objects.filter(id=int(curso_id)).first() if curso_id.isdigit() else None

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    nombre_curso = curso.nombre.replace(" ", "_").replace('"', "") if curso else "Curso"
    response["Content-Disposition"] = f'attachment; filename="III_Trimestre_{tipo.upper()}_{nombre_curso}.csv"'

    writer = csv.writer(response, delimiter=";")
    if not curso:
        return response

    estudiantes = sorted(EstudiantePerfil.objects.filter(curso=curso), key=_clave_orden)

    fechas_asist = list(
        RegistroAsistencia.objects.filter(estudiante__curso=curso)
        .values_list("fecha", flat=True)
        .distinct()
        .order_by("fecha")
    )
    mapa_asist = {(a.estudiante_id, a.fecha): a.estado for a in RegistroAsistencia.objects.filter(estudiante__curso=curso)}

    fechas_piz = list(
        RegistroPizarra.objects.filter(estudiante__curso=curso)
        .values_list("fecha", flat=True)
        .distinct()
        .order_by("fecha")
    )
    mapa_piz = {(p.estudiante_id, p.fecha): float(p.nota_cuanti) for p in RegistroPizarra.objects.filter(estudiante__curso=curso)}

    if tipo == "asistencia":
        encabezado = (
            ["N°", "Apellidos y Nombres", "Cédula"]
            + [f.strftime("%d/%m/%Y") for f in fechas_asist]
            + ["P", "F", "A", "J", "% Asistencia Trimestral"]
        )
        writer.writerow(encabezado)

        for idx, est in enumerate(estudiantes, start=1):
            fila = [idx, est.nombre_completo, est.cedula]
            cnt_p = cnt_f = cnt_a = cnt_j = 0
            for f in fechas_asist:
                val = mapa_asist.get((est.id, f), "-")
                fila.append(val)
                if val == "P":
                    cnt_p += 1
                elif val == "F":
                    cnt_f += 1
                elif val == "A":
                    cnt_a += 1
                elif val == "J":
                    cnt_j += 1
            marcadas = cnt_p + cnt_f + cnt_a + cnt_j
            asistidas = cnt_p + cnt_a + cnt_j
            pct = round((asistidas / marcadas) * 100, 1) if marcadas > 0 else 0.0
            fila.extend([cnt_p, cnt_f, cnt_a, cnt_j, f"{pct}%".replace(".", ",")])
            writer.writerow(fila)

    elif tipo == "pizarra":
        encabezado = (
            ["N°", "Apellidos y Nombres", "Cédula"]
            + [f.strftime("%d/%m/%Y") for f in fechas_piz]
            + ["N° Lecciones", "Promedio Pizarra Trimestral"]
        )
        writer.writerow(encabezado)

        for idx, est in enumerate(estudiantes, start=1):
            fila = [idx, est.nombre_completo, est.cedula]
            notas = []
            for f in fechas_piz:
                if (est.id, f) in mapa_piz:
                    n = mapa_piz[(est.id, f)]
                    notas.append(n)
                    fila.append(f"{n:.2f}".replace(".", ","))
                else:
                    fila.append("-")
            prom = round(sum(notas) / len(notas), 2) if notas else 0.0
            fila.extend([len(notas), f"{prom:.2f}".replace(".", ",") if notas else "-"])
            writer.writerow(fila)

    else:
        # CONSOLIDADO FINAL DEL III TRIMESTRE (ASISTENCIA + PIZARRA)
        encabezado = [
            "N°",
            "Apellidos y Nombres",
            "Cédula",
            "Presentes (P)",
            "Faltas (F)",
            "Atrasos (A)",
            "Justificadas (J)",
            "% Asistencia Trimestral",
            "N° Pizarras",
            "Promedio Pizarra Trimestral",
        ]
        writer.writerow(encabezado)

        for idx, est in enumerate(estudiantes, start=1):
            cnt_p = cnt_f = cnt_a = cnt_j = 0
            for f in fechas_asist:
                val = mapa_asist.get((est.id, f))
                if val == "P":
                    cnt_p += 1
                elif val == "F":
                    cnt_f += 1
                elif val == "A":
                    cnt_a += 1
                elif val == "J":
                    cnt_j += 1
            marcadas = cnt_p + cnt_f + cnt_a + cnt_j
            asistidas = cnt_p + cnt_a + cnt_j
            pct = round((asistidas / marcadas) * 100, 1) if marcadas > 0 else 0.0

            notas = [mapa_piz[(est.id, f)] for f in fechas_piz if (est.id, f) in mapa_piz]
            prom = round(sum(notas) / len(notas), 2) if notas else 0.0

            writer.writerow([
                idx,
                est.nombre_completo,
                est.cedula,
                cnt_p,
                cnt_f,
                cnt_a,
                cnt_j,
                f"{pct}%".replace(".", ","),
                len(notas),
                f"{prom:.2f}".replace(".", ",") if notas else "-",
            ])

    return response