import re
import os
import io
import csv
import json
import time
import base64
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from urllib.parse import quote
from PIL import Image

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Avg, Q
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST

from .models import (
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


def _optimizar_imagen_b64(archivo):
    img = Image.open(archivo)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if max(img.size) > 1280:
        img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _detectar_especialidad_paralelo(nombre_curso):
    texto = (nombre_curso or "").lower()
    esp = "Informática"
    if "contab" in texto:
        esp = "Contabilidad"
    elif "inform" in texto:
        esp = "Informática"
    elif "venta" in texto:
        esp = "Ventas"
    elif "agrop" in texto:
        esp = "Agropecuaria"

    par = "A"
    for letra in ["A", "B", "C"]:
        if (
            f"'{letra.lower()}'" in texto
            or f'"{letra.lower()}"' in texto
            or texto.endswith(f" {letra.lower()}")
        ):
            par = letra
            break
    return esp, par


def _formatear_whatsapp_ec(telefono):
    limpio = "".join(c for c in (telefono or "") if c.isdigit())
    if not limpio:
        return ""
    if limpio.startswith("0") and len(limpio) == 10:
        return "593" + limpio[1:]
    if limpio.startswith("593"):
        return limpio
    return limpio


def _es_titulo_eis(titulo):
    t = (titulo or "").strip().upper()
    return t.startswith("[EIS]") or t.startswith("[MÓDULO IA]") or t.startswith("[MODULO IA]") or "(EIS)" in t


def _gemini_url(k):
    k = (k or "").strip().strip('"').strip("'")
    pref = [
        "models/gemini-3.5-flash-lite",
        "models/gemini-3.1-flash-lite",
        "models/gemini-2.5-flash-lite",
        "models/gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.5-flash",
    ]
    try:
        u = f"https://generativelanguage.googleapis.com/v1beta/models?key={k}"
        d = json.loads(urllib.request.urlopen(u, timeout=15).read().decode("utf-8"))
        ms = [
            m["name"] for m in d.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "gemini" in m.get("name", "").lower()
            and not any(x in m.get("name", "").lower() for x in ("tts", "image", "audio", "embedding", "exp", "preview", "1.5", "2.0", "vision", "aqa", "veo"))
        ]
        for m in pref:
            if m in ms:
                return f"https://generativelanguage.googleapis.com/v1beta/{m}:generateContent?key={k}"
        fl = sorted([m for m in ms if "flash" in m.lower()], reverse=True)
        if fl:
            return f"https://generativelanguage.googleapis.com/v1beta/{fl[0]}:generateContent?key={k}"
        if ms:
            return f"https://generativelanguage.googleapis.com/v1beta/{sorted(ms, reverse=True)[0]}:generateContent?key={k}"
    except Exception:
        pass
    return f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={k}"


def _llamar_gemini_json(api_key, base_url, parts):
    base_part, q_part = base_url.split("?", 1) if "?" in base_url else (base_url, "")
    k = ""
    for seg in q_part.split("&"):
        if seg.startswith("key="):
            k = seg[4:]

    cands = [base_url]
    if k:
        for alt in (
            "models/gemini-3.5-flash-lite",
            "models/gemini-2.5-flash-lite",
            "models/gemini-3.8-flash",
            "models/gemini-flash-latest",
        ):
            u_alt = f"https://generativelanguage.googleapis.com/v1beta/{alt}:generateContent?key={k}"
            if u_alt not in cands:
                cands.append(u_alt)

    last_err = None
    for u_try in cands[:4]:
        es_25 = "2.5" in u_try
        thinking_cfg = {"thinkingBudget": 0} if es_25 else {"thinkingLevel": "LOW"}

        for usar_thinking in (True, False):
            gen_cfg = {
                "responseMimeType": "application/json",
                "temperature": 0.3,
            }
            if usar_thinking:
                gen_cfg["thinkingConfig"] = thinking_cfg

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": gen_cfg,
            }
            req = urllib.request.Request(
                u_try,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=75) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
            except urllib.error.HTTPError as he:
                err_txt = ""
                try:
                    err_txt = he.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                last_err = Exception(f"HTTP {he.code} [{u_try.split('/')[-1].split('?')[0]}]: {err_txt[:220]}")
                if he.code == 400 and "thinking" in err_txt.lower() and usar_thinking:
                    continue
                if he.code in (404, 429, 500, 502, 503, 504):
                    time.sleep(0.5)
                    break
                raise last_err
            except Exception as te:
                last_err = Exception(f"{te} [{u_try.split('/')[-1].split('?')[0]}]")
                break

    if last_err:
        raise last_err
    raise Exception("No se pudo obtener respuesta de Gemini.")


@staff_member_required
def panel_docente_institucional(request):
    cursos = list(CursoBGU.objects.all().order_by("nombre"))
    curso_id = request.GET.get("curso_id", "")
    exportar = request.GET.get("exportar", "")

    estudiantes_qs = EstudiantePerfil.objects.select_related("curso", "user").order_by(
        "curso__nombre", "apellidos_nombres", "user__last_name"
    )
    if curso_id:
        estudiantes_qs = estudiantes_qs.filter(curso_id=curso_id)

    estudiantes = list(estudiantes_qs)
    est_ids = [e.id for e in estudiantes]

    prom_entregas = defaultdict(dict)
    for row in (
        EntregaTarea.objects.filter(estudiante_id__in=est_ids)
        .values("estudiante_id", "tarea__tipo_tarea")
        .annotate(p=Avg("nota_calculada"))
    ):
        prom_entregas[row["estudiante_id"]][row["tarea__tipo_tarea"]] = float(row["p"] or 0)

    filtro_eis = (
        Q(evaluacion__titulo__startswith="[EIS]")
        | Q(evaluacion__titulo__startswith="[Módulo IA]")
        | Q(evaluacion__titulo__startswith="[Modulo IA]")
        | Q(evaluacion__titulo__icontains="(EIS)")
    )

    eis_nota_unica_map = {}
    for row in (
        ResultadoEvaluacion.objects.filter(estudiante_id__in=est_ids)
        .filter(filtro_eis)
        .order_by("fecha_registro", "id")
        .values("estudiante_id", "nota_obtenida")
    ):
        eis_nota_unica_map[row["estudiante_id"]] = float(row["nota_obtenida"] or 0)

    prom_evals_online_map = {}
    for row in (
        ResultadoEvaluacion.objects.filter(estudiante_id__in=est_ids)
        .exclude(filtro_eis)
        .values("estudiante_id")
        .annotate(p=Avg("nota_obtenida"))
    ):
        prom_evals_online_map[row["estudiante_id"]] = float(row["p"] or 0)

    PESOS_ASISTENCIA = {
        "P": 1.0,
        "J": 0.9,
        "A": 0.7,
        "F": 0.0,
        "FG": 0.0,
        "FUGA": 0.0,
    }
    asist_stats = defaultdict(lambda: [0.0, 0])
    for row in RegistroAsistencia.objects.filter(estudiante_id__in=est_ids).values("estudiante_id", "estado"):
        est_code = (row["estado"] or "").strip().upper()
        if est_code in PESOS_ASISTENCIA:
            asist_stats[row["estudiante_id"]][1] += 1
            asist_stats[row["estudiante_id"]][0] += PESOS_ASISTENCIA[est_code]

    prom_pizarra_map = {}
    for row in (
        RegistroPizarra.objects.filter(estudiante_id__in=est_ids)
        .values("estudiante_id")
        .annotate(p=Avg("nota_cuanti"))
    ):
        prom_pizarra_map[row["estudiante_id"]] = float(row["p"] or 0)

    tareas_por_curso = defaultdict(int)
    for t in Tarea.objects.all().values("id", "curso_id"):
        tareas_por_curso[t["curso_id"]] += 1

    evals_por_curso = defaultdict(int)
    for ev in Evaluacion.objects.all().values("id", "curso_id"):
        evals_por_curso[ev["curso_id"]] += 1

    tareas_ok_por_est = defaultdict(set)
    for row in EntregaTarea.objects.filter(
        estudiante_id__in=est_ids, nota_calculada__gte=7
    ).values("estudiante_id", "tarea_id"):
        tareas_ok_por_est[row["estudiante_id"]].add(row["tarea_id"])

    evals_ok_por_est = defaultdict(set)
    for row in ResultadoEvaluacion.objects.filter(
        estudiante_id__in=est_ids, nota_obtenida__gte=7
    ).values("estudiante_id", "evaluacion_id"):
        evals_ok_por_est[row["estudiante_id"]].add(row["evaluacion_id"])

    filas = []
    total_con_pendientes = 0
    total_activos = 0

    for est in estudiantes:
        es_retirado = bool(est.retirado)
        if not es_retirado:
            total_activos += 1

        p_mat = prom_entregas[est.id].get("MATERIA", 0.0)
        p_deb = prom_entregas[est.id].get("DEBER", 0.0)
        p_tal = prom_entregas[est.id].get("TALLER", 0.0)
        nota_eis = eis_nota_unica_map.get(est.id, 0.0)
        p_eva = prom_evals_online_map.get(est.id, 0.0)

        puntos_asist, marcadas = asist_stats[est.id]
        p_actuacion = round((puntos_asist / marcadas) * 10.0, 2) if marcadas > 0 else 0.0
        p_pizarra = prom_pizarra_map.get(est.id, 0.0)

        notas_activas = [n for n in (p_mat, p_deb, p_tal, p_actuacion, p_pizarra, nota_eis, p_eva) if n > 0]
        promedio_final = round(sum(notas_activas) / len(notas_activas), 2) if notas_activas else 0.0

        if es_retirado:
            pendientes = 0
        else:
            tot_t = tareas_por_curso.get(est.curso_id, 0)
            ok_t = len(tareas_ok_por_est.get(est.id, set()))
            tot_e = evals_por_curso.get(est.curso_id, 0)
            ok_e = len(evals_ok_por_est.get(est.id, set()))
            pendientes = max(0, (tot_t - ok_t) + (tot_e - ok_e))
            if pendientes > 0:
                total_con_pendientes += 1

        filas.append(
            {
                "estudiante": est,
                "retirado": es_retirado,
                "materia": round(p_mat, 2),
                "deberes": round(p_deb, 2),
                "talleres": round(p_tal, 2),
                "actuacion_clase": p_actuacion,
                "leccion_pizarra": round(p_pizarra, 2),
                "eis": round(nota_eis, 2),
                "evaluaciones": round(p_eva, 2),
                "promedio": promedio_final,
                "pendientes": pendientes,
            }
        )

    if exportar == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="Calificaciones_UE_Enrique_Noboa.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(['UNIDAD EDUCATIVA TÉCNICA "DR. ENRIQUE NOBOA" - LA TRONCAL'])
        writer.writerow(
            [
                "Cédula",
                "Apellidos y Nombres",
                "Curso",
                "Estado",
                "Materia",
                "Deberes",
                "Talleres",
                "Actuación en Clase (/10)",
                "Lección / Pizarra",
                "EIS",
                "Evaluación Online",
                "Promedio General",
                "Actividades Pendientes",
            ]
        )
        for f in filas:
            writer.writerow(
                [
                    f["estudiante"].cedula,
                    f["estudiante"].nombre_completo,
                    f["estudiante"].curso.nombre,
                    "RETIRADO" if f["retirado"] else "ACTIVO",
                    f["materia"],
                    f["deberes"],
                    f["talleres"],
                    f["actuacion_clase"],
                    f["leccion_pizarra"],
                    f["eis"],
                    f["evaluaciones"],
                    f["promedio"],
                    "RETIRADO" if f["retirado"] else f["pendientes"],
                ]
            )
        return response

    try:
        total_modulos = ModuloInteractivo.objects.count()
    except Exception:
        total_modulos = 0

    return render(
        request,
        "cursos/panel_docente.html",
        {
            "cursos": cursos,
            "curso_id_actual": curso_id,
            "filas": filas,
            "total_estudiantes": total_activos,
            "total_modulos": total_modulos,
            "total_con_pendientes": total_con_pendientes,
        },
    )


@staff_member_required
def crear_modulo_ia(request):
    cursos = CursoBGU.objects.all().order_by("nombre")
    tareas = Tarea.objects.all().order_by("-id")[:30]
    modulos_recientes = list(ModuloInteractivo.objects.select_related("curso", "evaluacion_vinculada")[:12])
    for m in modulos_recientes:
        tit_ev = m.evaluacion_vinculada.titulo if m.evaluacion_vinculada else m.titulo
        m.es_eis = _es_titulo_eis(tit_ev)

    error_msg = None

    if request.method == "POST":
        _normalizar_curso_bgu_post(request)
        _raw_curso = (request.POST.get("curso") or request.POST.get("curso_id") or "").strip()
        if _raw_curso in ("2DO_BGU", "3ERO_BGU"):
            _pref = "2DO" if _raw_curso == "2DO_BGU" else "3RO"
            _esp_in = (request.POST.get("especialidad") or "").strip().lower()
            _par_in = (request.POST.get("paralelo") or "").strip().lower()
            _par_letra = re.sub(r"^paralelo\s+", "", _par_in).strip()
            def _es_nivel(nom):
                low = (nom or "").strip().lower()
                if _pref == "2DO":
                    return bool(re.match(r"^(2do|2°|segundo)\b", low))
                return bool(re.match(r"^(3ro|3°|tercero)\b", low))
            _candidatos = [c for c in CursoBGU.objects.all().order_by("id") if _es_nivel(c.nombre)]
            _elegido = None
            for _c in _candidatos:
                _cn = _c.nombre.lower()
                if (_esp_in and _esp_in in _cn) and (_par_letra and re.search(rf"['\"\s]{re.escape(_par_letra)}(?:['\"\s]|$)", _cn)):
                    _elegido = _c
                    break
            if not _elegido and _esp_in:
                for _c in _candidatos:
                    if _esp_in in _c.nombre.lower():
                        _elegido = _c
                        break
            if not _elegido and _candidatos:
                _elegido = _candidatos[0]
            if _elegido:
                _post_mut = request.POST.copy()
                _post_mut["curso"] = str(_elegido.id)
                _post_mut["curso_id"] = str(_elegido.id)
                request.POST = _post_mut

        titulo = request.POST.get("titulo", "").strip()
        asignatura = request.POST.get("asignatura", "Matemática").strip()
        institucion = request.POST.get(
            "institucion", 'UNIDAD EDUCATIVA TÉCNICA "DR. ENRIQUE NOBOA" • LA TRONCAL'
        ).strip()
        curso_id = request.POST.get("curso_id")
        especialidad = request.POST.get("especialidad", "Informática")
        paralelo = request.POST.get("paralelo", "A")
        destreza = request.POST.get("destreza_indicadores", "").strip()
        tiempo_minutos = int(request.POST.get("tiempo_minutos") or 30)
        tarea_id = request.POST.get("tarea_id") or None
        destino_sabana = (request.POST.get("destino_sabana") or "EVALUACION").strip().upper()
        es_eis = (destino_sabana == "EIS")
        fotos = request.FILES.getlist("fotos_texto")

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            error_msg = "Falta configurar la variable GEMINI_API_KEY en Render."
        elif not titulo or not curso_id:
            error_msg = "Debes ingresar el tema del módulo y seleccionar el curso."
        else:
            curso = get_object_or_404(CursoBGU, id=curso_id)
            destreza_txt = destreza if destreza else "Alineado al currículo vigente del Ministerio de Educación de Ecuador."

            prompt_parte1 = f"""
Eres docente de Bachillerato en Ecuador (U.E. Técnica "Dr. Enrique Noboa" - La Troncal).
Genera la guía didáctica sencilla y directa sobre:
- Tema: {titulo}
- Asignatura: {asignatura}
- Curso: {curso.nombre}
- Destreza e Indicadores: {destreza_txt}
{"- Analiza también las imágenes adjuntas del texto escolar y extrae fielmente sus conceptos y ejercicios." if fotos else ""}

REGLAS:
1. Usa LaTeX entre $...$ solo para fórmulas matemáticas (ej. $a_n = 3n + 1$, $\\frac{{2k+1}}{{k}}$). NUNCA pongas palabras en español ni \\text{{...}} dentro de $...$.
2. Explicaciones y pasos muy claros y cortos (máximo 1 o 2 líneas), sin textos largos ni enfoques de especialidad técnica.
3. Devuelve ÚNICAMENTE un JSON válido con esta estructura:
{{
  "subtitulo": "Frase corta descriptiva del módulo",
  "notacion_general": "Fórmula o principio central en LaTeX o texto corto",
  "anatomia_pasos": [
    {{"paso": "1. TÍTULO CORTO", "expresion": "Fórmula o ejemplo breve"}},
    {{"paso": "2. TÍTULO CORTO", "expresion": "Fórmula o ejemplo breve"}},
    {{"paso": "3. TÍTULO CORTO", "expresion": "Fórmula o ejemplo breve"}},
    {{"paso": "4. TÍTULO CORTO", "expresion": "Resultado o conclusión"}}
  ],
  "tarjetas_infografia": [
    {{
      "numero": 1,
      "titulo": "Subtema 1",
      "color": "blue",
      "explicacion": "Explicación clara y directa",
      "formula_clave": "Fórmula o regla destacada",
      "ejemplo_enunciado": "Enunciado del ejercicio resuelto",
      "ejemplo_pasos": ["Paso 1...", "Paso 2..."],
      "ejemplo_respuesta": "Respuesta final clara"
    }}
  ],
  "tarea_guiada": [
    {{
      "numero": 1,
      "categoria": "SUBTEMA",
      "pregunta": "Enunciado de entrenamiento",
      "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "indice_correcto": 0,
      "explicacion": "Explicación breve de por qué esa es la respuesta"
    }}
  ],
  "deber_casa": [
    {{
      "numero": 1,
      "tema": "Etiqueta corta",
      "enunciado": "Ejercicio propuesto para resolver en el cuaderno"
    }}
  ]
}}
CANTIDADES EXACTAS: "anatomia_pasos" (4), "tarjetas_infografia" (5 con colores: "blue", "emerald", "purple", "amber", "rose"), "tarea_guiada" (6), "deber_casa" (10).
"""

            prompt_parte2 = f"""
Eres docente de Bachillerato en Ecuador (U.E. Técnica "Dr. Enrique Noboa" - La Troncal).
Genera una evaluación de 20 preguntas de opción múltiple claras y didácticas sobre:
- Tema: {titulo}
- Asignatura: {asignatura}
- Curso: {curso.nombre}
- Destreza e Indicadores: {destreza_txt}
{"- Toma en cuenta también las imágenes adjuntas del texto escolar." if fotos else ""}

REGLAS:
1. Usa LaTeX entre $...$ solo para fórmulas matemáticas (ej. $\\bar{{x}} = 12$). NUNCA pongas palabras en español ni \\text{{...}} dentro de $...$.
2. Preguntas y opciones concisas y directas.
3. Devuelve ÚNICAMENTE un JSON válido con exactamente 20 preguntas:
{{
  "evaluacion_20": [
    {{
      "numero": 1,
      "pregunta": "Enunciado de la pregunta",
      "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "indice_correcto": 0
    }}
  ]
}}
"""

            imagenes_b64 = []
            for foto in fotos[:3]:
                imagenes_b64.append(_optimizar_imagen_b64(foto))

            parts_1 = [{"text": prompt_parte1}]
            parts_2 = [{"text": prompt_parte2}]
            for b64_img in imagenes_b64:
                inline = {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                parts_1.append(inline)
                parts_2.append(inline)

            url = _gemini_url(api_key)
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    fut_1 = pool.submit(_llamar_gemini_json, api_key, url, parts_1)
                    fut_2 = pool.submit(_llamar_gemini_json, api_key, url, parts_2)
                    res_1 = fut_1.result()
                    res_2 = fut_2.result()

                parsed = {
                    "subtitulo": res_1.get("subtitulo", titulo),
                    "notacion_general": res_1.get("notacion_general", ""),
                    "anatomia_pasos": res_1.get("anatomia_pasos", []),
                    "tarjetas_infografia": res_1.get("tarjetas_infografia", []),
                    "tarea_guiada": res_1.get("tarea_guiada", []),
                    "deber_casa": res_1.get("deber_casa", []),
                    "evaluacion_20": res_2.get("evaluacion_20", []),
                }

                # Prefijo que dirige automáticamente la calificación a EIS o a Evaluación Online
                # y mantiene la conexión directa con /aula/ (Portal del Estudiante)
                prefijo_eval = "[EIS]" if es_eis else "[Evaluación IA]"
                titulo_eval_vinculada = f"{prefijo_eval} {titulo}"

                evaluacion = Evaluacion.objects.create(
                    titulo=titulo_eval_vinculada,
                    curso=curso,
                )
                tarea_obj = Tarea.objects.filter(id=tarea_id).first() if tarea_id else None

                def _nivel_grupo(nombre_curso):
                    low = (nombre_curso or "").strip().lower()
                    if re.match(r"^(2do|2°|segundo)\b", low):
                        return "2DO"
                    if re.match(r"^(3ro|3°|tercero)\b", low):
                        return "3RO"
                    return None

                def _clonar_registro(obj, curso_dest):
                    if obj is None:
                        return None
                    if getattr(obj, "curso_id", None) == curso_dest.id:
                        return obj
                    cls = obj.__class__
                    kwargs = {}
                    for f in cls._meta.fields:
                        if f.primary_key:
                            continue
                        if f.name == "curso":
                            kwargs["curso"] = curso_dest
                        else:
                            kwargs[f.name] = getattr(obj, f.attname)
                    if cls.__name__ == "Tarea":
                        existente = cls.objects.filter(titulo=kwargs.get("titulo"), curso=curso_dest).first()
                        if existente:
                            return existente
                    return cls.objects.create(**kwargs)

                aplicar_todos = (
                    request.POST.get("aplicar_todos_nivel") == "1"
                    if "aplicar_todos_nivel_presente" in request.POST
                    else True
                )
                grupo = _nivel_grupo(curso.nombre if curso else "")
                cursos_destino = [curso] if curso else []
                if aplicar_todos and grupo:
                    todos_nivel = [
                        c for c in CursoBGU.objects.all().order_by("id")
                        if _nivel_grupo(c.nombre) == grupo
                    ]
                    if todos_nivel:
                        cursos_destino = [curso] + [c for c in todos_nivel if c.id != curso.id]

                modulo_principal = None
                json_base = json.dumps(parsed, ensure_ascii=False)
                for c_dest in cursos_destino:
                    if c_dest.id == curso.id:
                        eval_dest = evaluacion
                        tarea_dest = tarea_obj
                        esp_dest = especialidad
                        par_dest = paralelo
                        json_dest = json_base
                    else:
                        eval_dest = _clonar_registro(evaluacion, c_dest)
                        tarea_dest = _clonar_registro(tarea_obj, c_dest)
                        esp_dest, par_dest = _detectar_especialidad_paralelo(c_dest.nombre)
                        esp_dest = esp_dest or especialidad
                        par_dest = par_dest or paralelo
                        json_dest = json_base
                        if curso and curso.nombre and c_dest.nombre:
                            json_dest = json_dest.replace(curso.nombre, c_dest.nombre)
                            json_dest = json_dest.replace(curso.nombre.upper(), c_dest.nombre.upper())

                    mod_creado = ModuloInteractivo.objects.create(
                        titulo=titulo,
                        asignatura=asignatura,
                        institucion=institucion,
                        curso=c_dest,
                        especialidad=esp_dest,
                        paralelo=par_dest,
                        destreza_indicadores=destreza,
                        tiempo_minutos=tiempo_minutos,
                        contenido_json=json_dest,
                        evaluacion_vinculada=eval_dest,
                        tarea_deber_vinculada=tarea_dest,
                    )
                    if modulo_principal is None:
                        modulo_principal = mod_creado

                return redirect("ver_modulo_interactivo", modulo_id=modulo_principal.id)
            except Exception as e:
                error_msg = f"Ocurrió un inconveniente al generar con Gemini: {str(e)}"

    return render(
        request,
        "cursos/generar_modulo_ia.html",
        {
            "cursos": cursos,
            "tareas": tareas,
            "modulos_recientes": modulos_recientes,
            "error_msg": error_msg,
        },
    )


def ver_modulo_interactivo(request, modulo_id):
    modulo = get_object_or_404(ModuloInteractivo, id=modulo_id)
    contenido = json.loads(modulo.contenido_json)
    cedula_inicial = request.GET.get("cedula", "").strip()
    estudiante_inicial = None
    if cedula_inicial:
        estudiante_inicial = EstudiantePerfil.objects.filter(cedula=cedula_inicial).first()

    return render(
        request,
        "cursos/modulo_interactivo.html",
        {
            "modulo": modulo,
            "contenido": contenido,
            "contenido_json_str": modulo.contenido_json,
            "cedula_inicial": cedula_inicial,
            "estudiante_inicial": estudiante_inicial,
        },
    )


def api_buscar_estudiante(request):
    cedula = request.GET.get("cedula", "").strip()
    est = EstudiantePerfil.objects.filter(cedula=cedula).select_related("curso", "user").first()
    if not est:
        return JsonResponse({"encontrado": False})
    esp, par = _detectar_especialidad_paralelo(est.curso.nombre if est.curso else "")
    return JsonResponse(
        {
            "encontrado": True,
            "nombre": est.nombre_completo,
            "curso": est.curso.nombre if est.curso else "",
            "especialidad": esp,
            "paralelo": par,
        }
    )


@require_POST
def api_guardar_evaluacion_modulo(request, modulo_id):
    modulo = get_object_or_404(ModuloInteractivo, id=modulo_id)
    try:
        body = json.loads(request.body.decode("utf-8"))
        cedula = str(body.get("cedula", "")).strip()
        aciertos = int(body.get("aciertos", 0))
        total = int(body.get("total", 20)) or 20
        nota_10 = round((aciertos / total) * 10.0, 2)

        est = EstudiantePerfil.objects.filter(cedula=cedula).first()
        if not est:
            return JsonResponse(
                {"ok": False, "mensaje": "Cédula no encontrada en la nómina del colegio."}, status=400
            )

        if modulo.evaluacion_vinculada:
            ya_existe = ResultadoEvaluacion.objects.filter(
                estudiante=est, evaluacion=modulo.evaluacion_vinculada
            ).first()
            if ya_existe:
                return JsonResponse(
                    {
                        "ok": True,
                        "ya_registrada": True,
                        "nota_20": aciertos,
                        "nota_10": float(ya_existe.nota_obtenida),
                        "mensaje": f"Ya tenías registrada tu calificación oficial de {ya_existe.nota_obtenida}/10.",
                    }
                )
            ResultadoEvaluacion.objects.create(
                estudiante=est,
                evaluacion=modulo.evaluacion_vinculada,
                nota_obtenida=nota_10,
            )

        return JsonResponse(
            {
                "ok": True,
                "ya_registrada": False,
                "nota_20": aciertos,
                "nota_10": nota_10,
                "mensaje": f"¡Evaluación registrada! Obtuviste {aciertos}/{total} puntos (Equivalente a {nota_10}/10).",
            }
        )
    except Exception as e:
        return JsonResponse({"ok": False, "mensaje": str(e)}, status=400)


@staff_member_required
def centro_esquelas(request):
    cursos = list(CursoBGU.objects.all().order_by("nombre"))
    curso_id = request.GET.get("curso_id", "")

    if request.method == "POST":
        _normalizar_curso_bgu_post(request)
        accion = request.POST.get("accion")
        est_id = request.POST.get("estudiante_id")
        est = get_object_or_404(EstudiantePerfil, id=est_id)
        if accion == "guardar_telefono":
            est.telefono_representante = request.POST.get("telefono_representante", "").strip()
            est.save()
        elif accion == "registrar_esquela":
            detalle = request.POST.get("detalle_incumplimiento", "").strip()
            plazo = request.POST.get("plazo_entrega", "48 horas hábiles").strip()
            EsquelaIncumplimiento.objects.create(
                estudiante=est,
                detalle_incumplimiento=detalle,
                plazo_entrega=plazo,
                enviada_whatsapp=True,
            )
        return redirect(f"{request.path}?curso_id={curso_id}")

    estudiantes_qs = EstudiantePerfil.objects.select_related("curso", "user").filter(
        retirado=False
    ).order_by(
        "curso__nombre", "apellidos_nombres", "user__last_name"
    )
    if curso_id:
        estudiantes_qs = estudiantes_qs.filter(curso_id=curso_id)

    estudiantes = list(estudiantes_qs)
    est_ids = [e.id for e in estudiantes]

    tareas_por_curso = defaultdict(list)
    for t in Tarea.objects.all():
        tareas_por_curso[t.curso_id].append(t)

    evals_por_curso = defaultdict(list)
    for ev in Evaluacion.objects.all():
        evals_por_curso[ev.curso_id].append(ev)

    entregas_map = {}
    for ent in EntregaTarea.objects.filter(estudiante_id__in=est_ids).order_by("nota_calculada"):
        entregas_map[(ent.estudiante_id, ent.tarea_id)] = ent

    resultados_map = {}
    for res in ResultadoEvaluacion.objects.filter(estudiante_id__in=est_ids).order_by(
        "nota_obtenida"
    ):
        resultados_map[(res.estudiante_id, res.evaluacion_id)] = res

    reporte = []
    for est in estudiantes:
        pendientes = []
        for t in tareas_por_curso.get(est.curso_id, []):
            ent = entregas_map.get((est.id, t.id))
            if not ent or ent.nota_calculada < 7:
                estado_txt = f"Nota baja ({ent.nota_calculada}/10)" if ent else "Sin entregar"
                pendientes.append(f"[{t.get_tipo_tarea_display()}] {t.titulo} ({estado_txt})")

        for ev in evals_por_curso.get(est.curso_id, []):
            res = resultados_map.get((est.id, ev.id))
            if not res or res.nota_obtenida < 7:
                estado_txt = f"Nota baja ({res.nota_obtenida}/10)" if res else "No rendida"
                pendientes.append(f"[Lección/Evaluación] {ev.titulo} ({estado_txt})")

        faltas = len(pendientes)
        if faltas >= 3:
            semaforo = "rojo"
        elif faltas >= 1:
            semaforo = "amarillo"
        else:
            semaforo = "verde"

        detalle_texto = (
            "\n".join(f"• {p}" for p in pendientes) if pendientes else "Sin novedades académicas."
        )
        mensaje_wa = (
            f'UNIDAD EDUCATIVA TÉCNICA "DR. ENRIQUE NOBOA" - LA TRONCAL\n'
            f"ESQUELA DE NOTIFICACIÓN ACADÉMICA\n\n"
            f"Estimado/a Representante Legal de *{est.nombre_completo}* "
            f"(Curso: {est.curso.nombre}):\n"
            f"Le informamos que su representado/a registra las siguientes actividades académicas pendientes o por mejorar:\n\n"
            f"{detalle_texto}\n\n"
            f"Solicitamos su apoyo y seguimiento para regularizar estas actividades en un plazo máximo de 48 horas hábiles. "
            f"Atentamente, Docente de la Asignatura."
        )
        wa_num = _formatear_whatsapp_ec(est.telefono_representante)
        if wa_num:
            whatsapp_url = f"https://wa.me/{wa_num}?text={quote(mensaje_wa)}"
        else:
            whatsapp_url = f"https://api.whatsapp.com/send?text={quote(mensaje_wa)}"

        reporte.append(
            {
                "estudiante": est,
                "pendientes": pendientes,
                "detalle_texto": detalle_texto,
                "faltas": faltas,
                "semaforo": semaforo,
                "whatsapp_url": whatsapp_url,
            }
        )

    return render(
        request,
        "cursos/centro_esquelas.html",
        {
            "cursos": cursos,
            "curso_id_actual": curso_id,
            "reporte": reporte,
        },
    )


@staff_member_required
def imprimir_esquela(request, estudiante_id):
    est = get_object_or_404(EstudiantePerfil, id=estudiante_id)
    tareas_curso = Tarea.objects.filter(curso=est.curso)
    evals_curso = Evaluacion.objects.filter(curso=est.curso)

    entregas_ok = set(
        EntregaTarea.objects.filter(estudiante=est, nota_calculada__gte=7).values_list(
            "tarea_id", flat=True
        )
    )
    evals_ok = set(
        ResultadoEvaluacion.objects.filter(estudiante=est, nota_obtenida__gte=7).values_list(
            "evaluacion_id", flat=True
        )
    )

    items_pendientes = []
    for t in tareas_curso:
        if t.id not in entregas_ok:
            ent = EntregaTarea.objects.filter(estudiante=est, tarea=t).first()
            items_pendientes.append(
                {
                    "tipo": t.get_tipo_tarea_display(),
                    "actividad": t.titulo,
                    "estado": f"Calificación insuficiente ({ent.nota_calculada}/10)"
                    if ent
                    else "No presentado / Sin entrega",
                }
            )
    for ev in evals_curso:
        if ev.id not in evals_ok:
            res = ResultadoEvaluacion.objects.filter(estudiante=est, evaluacion=ev).first()
            items_pendientes.append(
                {
                    "tipo": "Evaluación / Lección",
                    "actividad": ev.titulo,
                    "estado": f"Calificación insuficiente ({res.nota_obtenida}/10)"
                    if res
                    else "Evaluación no rendida",
                }
            )

    esp, par = _detectar_especialidad_paralelo(est.curso.nombre if est.curso else "")
    EsquelaIncumplimiento.objects.create(
        estudiante=est,
        detalle_incumplimiento="; ".join(
            f"{i['tipo']}: {i['actividad']}" for i in items_pendientes
        )
        or "Revisión general",
    )

    return render(
        request,
        "cursos/esquela_oficial.html",
        {
            "estudiante": est,
            "especialidad": esp,
            "paralelo": par,
            "items_pendientes": items_pendientes,
            "fecha_hoy": timezone.now(),
        },
    )
