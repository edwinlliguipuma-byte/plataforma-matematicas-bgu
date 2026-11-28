import io
import unicodedata
import openpyxl
from openpyxl.workbook.protection import WorkbookProtection
from openpyxl.worksheet.protection import SheetProtection
from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import redirect
from .models import (
    CursoBGU,
    EstudiantePerfil,
    EntregaTarea,
    ResultadoEvaluacion,
    RegistroAsistencia,
    RegistroPizarra,
)


def _normalizar_texto(texto):
    txt = (texto or "").strip().upper()
    txt = "".join(
        c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
    )
    return " ".join(txt.split())


def _clave_alfabetica(est):
    return _normalizar_texto(est.nombre_completo)


def _detectar_modelo_eis():
    """Localiza dinámicamente el modelo de resultados de ModuloInteractivo (EIS) en la app cursos."""
    app_config = apps.get_app_config("cursos")
    for model in app_config.get_models():
        if model.__name__ in ("ResultadoEvaluacion", "EntregaTarea"):
            continue
        campos_fk = {
            f.name: f.related_model.__name__
            for f in model._meta.fields
            if getattr(f, "related_model", None) is not None
        }
        if "EstudiantePerfil" in campos_fk.values() and "ModuloInteractivo" in campos_fk.values():
            campo_est = next(k for k, v in campos_fk.items() if v == "EstudiantePerfil")
            campo_nota = None
            for f in model._meta.fields:
                if f.name in ("nota", "nota_obtenida", "calificacion", "puntaje"):
                    campo_nota = f.name
                    break
            if campo_nota:
                return model, campo_est, campo_nota
    return None, None, None


def _calcular_7_insumos_curso(curso):
    """
    Devuelve un diccionario {nombre_normalizado: [materia, deberes, talleres, act_clase, lecc_pizarra, eis, eval_online]}
    con los valores redondeados a 2 decimales.
    """
    estudiantes = sorted(
        EstudiantePerfil.objects.filter(curso=curso),
        key=_clave_alfabetica,
    )
    est_ids = [e.id for e in estudiantes]

    # 1. Tareas (Materia, Deberes, Talleres)
    notas_tareas = {eid: {"materia": [], "deber": [], "taller": []} for eid in est_ids}
    entregas = EntregaTarea.objects.select_related("tarea").filter(estudiante_id__in=est_ids)
    for ent in entregas:
        tipo = (ent.tarea.tipo_tarea or "").strip().lower()
        if tipo in notas_tareas and ent.nota_calculada is not None:
            notas_tareas[ent.estudiante_id][tipo].append(float(ent.nota_calculada))

    # 2. Asistencia -> Actuación en clase
    conteo_asist = {eid: {"asistidas": 0, "total": 0} for eid in est_ids}
    for reg in RegistroAsistencia.objects.filter(estudiante_id__in=est_ids):
        est_estado = (reg.estado or "").strip().upper()
        if est_estado in ("P", "F", "A", "J"):
            conteo_asist[reg.estudiante_id]["total"] += 1
            if est_estado in ("P", "A", "J"):
                conteo_asist[reg.estudiante_id]["asistidas"] += 1

    # 3. Lección / Pizarra
    notas_pizarra = {eid: [] for eid in est_ids}
    for reg in RegistroPizarra.objects.filter(estudiante_id__in=est_ids):
        if reg.nota_cuanti is not None:
            notas_pizarra[reg.estudiante_id].append(float(reg.nota_cuanti))

    # 4. EIS (Módulos Interactivos IA)
    notas_eis = {eid: [] for eid in est_ids}
    modelo_eis, campo_est_eis, campo_nota_eis = _detectar_modelo_eis()
    if modelo_eis:
        filtro = {f"{campo_est_eis}_id__in": est_ids}
        for reg in modelo_eis.objects.filter(**filtro):
            eid = getattr(reg, f"{campo_est_eis}_id")
            val = getattr(reg, campo_nota_eis, None)
            if val is not None:
                notas_eis[eid].append(float(val))

    # 5. Evaluación Online
    notas_eval = {eid: [] for eid in est_ids}
    for reg in ResultadoEvaluacion.objects.filter(estudiante_id__in=est_ids):
        if reg.nota_obtenida is not None:
            notas_eval[reg.estudiante_id].append(float(reg.nota_obtenida))

    def _prom(lista):
        return round(sum(lista) / len(lista), 2) if lista else 0.0

    resultado = {}
    for est in estudiantes:
        eid = est.id
        mat = _prom(notas_tareas[eid]["materia"])
        deb = _prom(notas_tareas[eid]["deber"])
        tal = _prom(notas_tareas[eid]["taller"])

        tot_a = conteo_asist[eid]["total"]
        asi_a = conteo_asist[eid]["asistidas"]
        act = round((asi_a / tot_a) * 10.0, 2) if tot_a > 0 else 0.0

        piz = _prom(notas_pizarra[eid])
        eis = _prom(notas_eis[eid])
        evl = _prom(notas_eval[eid])

        resultado[_normalizar_texto(est.nombre_completo)] = [
            mat,
            deb,
            tal,
            act,
            piz,
            eis,
            evl,
        ]

    return resultado


def _detectar_curso_desde_hoja(ws):
    """Cruza los nombres de B10:B49 del Excel con los cursos de la base de datos para detectar el curso exacto."""
    nombres_excel = set()
    for r in range(10, 50):
        val = ws.cell(row=r, column=2).value
        if val:
            nombres_excel.add(_normalizar_texto(str(val)))

    if not nombres_excel:
        return None

    mejor_curso = None
    mejor_coincidencias = 0
    for curso in CursoBGU.objects.all():
        estudiantes = EstudiantePerfil.objects.filter(curso=curso)
        coincidencias = sum(
            1 for e in estudiantes if _normalizar_texto(e.nombre_completo) in nombres_excel
        )
        if coincidencias > mejor_coincidencias:
            mejor_coincidencias = coincidencias
            mejor_curso = curso

    return mejor_curso if mejor_coincidencias >= 3 else None


@staff_member_required(login_url="/admin/login/")
def exportar_plantilla_xlsm(request):
    if request.method != "POST":
        return redirect("panel_docente")

    archivo = request.FILES.get("archivo_xlsm")
    if not archivo:
        return redirect("panel_docente")

    hoja_objetivo = (request.POST.get("trimestre") or "3er. Trim.").strip()
    curso_id = (request.POST.get("curso_id") or "").strip()
    omitir_sin_notas = request.POST.get("omitir_sin_notas") == "1"

    nombre_original = archivo.name or "Calificaciones_Actualizadas.xlsm"
    es_xlsm = nombre_original.lower().endswith(".xlsm")

    wb = openpyxl.load_workbook(archivo, keep_vba=es_xlsm)

    # Desproteger la estructura del libro y TODAS las hojas automáticamente
    wb.security = WorkbookProtection()
    for hoja in wb.worksheets:
        hoja.protection = SheetProtection(sheet=False)

    if hoja_objetivo in wb.sheetnames:
        ws = wb[hoja_objetivo]
    elif "3er. Trim." in wb.sheetnames:
        ws = wb["3er. Trim."]
    else:
        ws = wb.active

    curso = None
    if curso_id.isdigit():
        curso = CursoBGU.objects.filter(id=int(curso_id)).first()
    if not curso:
        curso = _detectar_curso_desde_hoja(ws)

    if curso:
        mapa_notas = _calcular_7_insumos_curso(curso)

        # Recorre filas 10 a 49 (nómina oficial) y escribe SOLO columnas F (6) a L (12)
        for fila in range(10, 50):
            celda_nombre = ws.cell(row=fila, column=2).value
            if not celda_nombre:
                continue

            clave = _normalizar_texto(str(celda_nombre))
            insumos = mapa_notas.get(clave)
            if not insumos:
                continue

            if omitir_sin_notas and all(v == 0.0 for v in insumos):
                continue

            for idx_col, valor in enumerate(insumos, start=6):  # Columnas 6=F hasta 12=L
                ws.cell(row=fila, column=idx_col).value = valor

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    content_type = (
        "application/vnd.ms-excel.sheet.macroEnabled.12"
        if es_xlsm
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{nombre_original}"'
    return response
