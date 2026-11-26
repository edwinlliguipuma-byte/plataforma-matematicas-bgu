import re
import os
import io
import csv
import json
import base64
import urllib.request
from collections import defaultdict
from urllib.parse import quote
from PIL import Image

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Avg
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


def _gemini_urlopen(req, timeout=165):
    import time, urllib.request, urllib.error
    orig_url = req.full_url if hasattr(req, "full_url") else str(req)
    if "generativelanguage.googleapis.com" not in orig_url or ":generateContent" not in orig_url:
        return urllib.request.urlopen(req, timeout=timeout)
    base_part, q_part = orig_url.split("?", 1) if "?" in orig_url else (orig_url, "")
    k = ""
    for seg in q_part.split("&"):
        if seg.startswith("key="):
            k = seg[4:]
    cands = [orig_url]
    if k:
        for alt in ("models/gemini-3.8-flash", "models/gemini-3.5-flash", "models/gemini-flash-latest", "models/gemini-3.0-flash"):
            u_alt = f"https://generativelanguage.googleapis.com/v1beta/{alt}:generateContent?key={k}"
            if u_alt not in cands:
                cands.append(u_alt)
    last_err = None
    for u_try in cands[:3]:
        r_try = urllib.request.Request(u_try, data=req.data, headers=dict(req.header_items()), method=req.get_method())
        try:
            return urllib.request.urlopen(r_try, timeout=165)
        except urllib.error.HTTPError as he:
            last_err = he
            if he.code in (404, 429, 500, 502, 503, 504):
                time.sleep(1.0)
                continue
            raise
    if last_err:
        raise last_err
    return urllib.request.urlopen(req, timeout=165)

def _gemini_url(k):
    import json, urllib.request
    k = (k or "").strip().strip('"').strip("'")
    pref = [
        "models/gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.0-flash",
        "models/gemini-flash-latest",
        "models/gemini-3.8-pro",
        "models/gemini-pro-latest",
    ]
    try:
        u = f"https://generativelanguage.googleapis.com/v1beta/models?key={k}"
        d = json.loads(urllib.request.urlopen(u, timeout=165).read().decode("utf-8"))
        ms = [
            m["name"] for m in d.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "gemini" in m.get("name", "").lower()
            and not any(x in m.get("name", "").lower() for x in ("tts", "image", "audio", "embedding", "exp", "preview", "1.5", "2.0", "2.5", "vision", "aqa", "veo"))
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
    return f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={k}"

@staff_member_required
def panel_docente_institucional(request):
    cursos = list(CursoBGU.objects.all().order_by("nombre"))
    curso_id = request.GET.get("curso_id", "")
    exportar = request.GET.get("exportar", "")

    estudiantes_qs = EstudiantePerfil.objects.select_related("curso", "user").order_by(
        "curso__nombre", "user__last_name", "apellidos_nombres"
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

    prom_evals_map = {}
    for row in (
        ResultadoEvaluacion.objects.filter(estudiante_id__in=est_ids)
        .values("estudiante_id")
        .annotate(p=Avg("nota_obtenida"))
    ):
        prom_evals_map[row["estudiante_id"]] = float(row["p"] or 0)

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

    for est in estudiantes:
        p_mat = prom_entregas[est.id].get("MATERIA", 0.0)
        p_deb = prom_entregas[est.id].get("DEBER", 0.0)
        p_tal = prom_entregas[est.id].get("TALLER", 0.0)
        p_eva = prom_evals_map.get(est.id, 0.0)

        notas_activas = [n for n in (p_mat, p_deb, p_tal, p_eva) if n > 0]
        promedio_final = round(sum(notas_activas) / len(notas_activas), 2) if notas_activas else 0.0

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
                "materia": round(p_mat, 2),
                "deberes": round(p_deb, 2),
                "talleres": round(p_tal, 2),
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
                "Materia",
                "Deberes",
                "Talleres",
                "Lecciones/Eval.",
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
                    f["materia"],
                    f["deberes"],
                    f["talleres"],
                    f["evaluaciones"],
                    f["promedio"],
                    f["pendientes"],
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
            "total_estudiantes": len(filas),
            "total_modulos": total_modulos,
            "total_con_pendientes": total_con_pendientes,
        },
    )


@staff_member_required
def crear_modulo_ia(request):
    cursos = CursoBGU.objects.all().order_by("nombre")
    tareas = Tarea.objects.all().order_by("-id")[:30]
    modulos_recientes = ModuloInteractivo.objects.all()[:10]
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
        fotos = request.FILES.getlist("fotos_texto")

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            error_msg = "Falta configurar la variable GEMINI_API_KEY en Render."
        elif not titulo or not curso_id:
            error_msg = "Debes ingresar el tema del módulo y seleccionar el curso."
        else:
            curso = get_object_or_404(CursoBGU, id=curso_id)
            prompt = f"""
Eres un docente especialista de Bachillerato Técnico en Ecuador (Unidad Educativa Técnica "Dr. Enrique Noboa" - La Troncal).
Genera un módulo didáctico completo, riguroso, claro y pedagógico sobre:
- Tema: {titulo}
- Asignatura: {asignatura}
- Curso: {curso.nombre} ({especialidad})
- Destreza e Indicadores de Evaluación: {destreza if destreza else "Alineado al currículo vigente del Ministerio de Educación de Ecuador."}
{"- Además analiza las imágenes adjuntas del texto/guía escolar y extrae fielmente sus conceptos, definiciones y ejercicios." if fotos else ""}

REGLAS DE FORMATO:
1. Usa notación LaTeX entre signos de dólar simples ($...$) para fórmulas matemáticas o científicas (ej. $a_n = 3n + 1$, $\\frac{{2k+1}}{{k}}$, $\\sqrt{{12-2k}}$).
2. Devuelve ÚNICAMENTE un objeto JSON válido con exactamente esta estructura:
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
      "explicacion": "Explicación paso a paso de por qué esa es la respuesta"
    }}
  ],
  "deber_casa": [
    {{
      "numero": 1,
      "tema": "Etiqueta corta",
      "enunciado": "Ejercicio propuesto para resolver en el cuaderno"
    }}
  ],
  "evaluacion_20": [
    {{
      "numero": 1,
      "pregunta": "Pregunta de evaluación",
      "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "indice_correcto": 0
    }}
  ]
}}

CANTIDADES EXACTAS OBLIGATORIAS:
- "anatomia_pasos": exactamente 4 elementos.
- "tarjetas_infografia": exactamente 5 tarjetas (colores en orden: "blue", "emerald", "purple", "amber", "rose").
- "tarea_guiada": exactamente 6 ejercicios de entrenamiento con explicación.
- "deber_casa": exactamente 10 ejercicios variados ordenados de menor a mayor dificultad.
- "evaluacion_20": exactamente 20 preguntas de opción múltiple (4 opciones cada una, indice_correcto de 0 a 3).
"""
            prompt += "\nFORMATO MATEMÁTICO: Envuelve TODA expresión matemática, exponente, fracción, integral o raíz entre signos de dólar ($...$), por ejemplo: $\\int (3x^2 + 4x - 5)\\,dx$ o $\\frac{x^3}{3}$. Nunca dejes comandos LaTeX sueltos sin $...$.\n"
            prompt += "\nREGLA DE VELOCIDAD Y CONCISION: Responde de forma directa y breve. Cada explicacion o paso de resolucion debe tener maximo 1 o 2 lineas cortas (sin rodeos), manteniendo todas las formulas matematicas entre $...$.\n"
            prompt += "\nREGLA DE ETIQUETAS (NO_TEXT_CMD): Nunca uses \\text{...} para frases en español; escribe el texto fuera de los signos $ y encierra solo las fórmulas matemáticas entre $...$ (ejemplo: $a_1$ primer término, $d = a_k - a_{k-1}$ diferencia).\n"
            # REGLA_MATERIA_SENCILLA_GENERAL
            if especialidad:
                prompt = prompt.replace(especialidad, "Matemática General")
            prompt += (
                "\nREGLA PEDAGÓGICA OBLIGATORIA (SIN ESPECIALIDAD Y FÁCIL DE ENTENDER):\n"
                "1. SIN ENFOQUE DE ESPECIALIDAD: NO adaptes el título, subtítulo, teoría ni ejercicios a Contabilidad, Informática ni a ninguna especialidad técnica. "
                "No escribas frases como 'aplicadas a Contabilidad' o 'para Informática'. Usa ejemplos cotidianos simples y universales válidos para cualquier estudiante de bachillerato.\n"
                "2. MATERIA RESUMIDA Y MUY SENCILLA: Explica la teoría y cada paso con palabras simples, claras y fáciles de entender para estudiantes que tienen dificultad en matemáticas. "
                "Evita definiciones largas o tecnicismos complicados. Usa frases cortas (máximo 1 o 2 líneas por idea), explica qué significa cada letra de la fórmula de forma sencilla y resuelve los ejemplos paso a paso con números claros.\n"
            )
            prompt += "\nREGLA ESTRICTA DE SIGNOS DE DÓLAR (NO_SPANISH_IN_DOLLARS): NUNCA metas palabras o preguntas en español dentro de $...$. Correcto: En la progresión $3, 9, 15, 21, \\dots$, ¿cuál es el término de la posición $8$? Incorrecto: $3, 9, 15, 21, \\dots, ¿cuál es el término 8$.\n"
            parts = [{"text": prompt}]
            for foto in fotos[:3]:
                b64_img = _optimizar_imagen_b64(foto)
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64_img}})

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.35,
                },
            }

            url = _gemini_url(api_key)
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with _gemini_urlopen(req, timeout=165) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)

                evaluacion = Evaluacion.objects.create(
                    titulo=f"[Módulo IA] {titulo}",
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
                        if "_detectar_especialidad_paralelo" in globals():
                            esp_dest, par_dest = _detectar_especialidad_paralelo(c_dest.nombre)
                            esp_dest = esp_dest or especialidad
                            par_dest = par_dest or paralelo
                        else:
                            esp_dest, par_dest = especialidad, paralelo
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
                _b = e.read().decode('utf-8', errors='ignore')[:260] if hasattr(e, 'read') else ''
                _u = locals().get('url', '').split('?')[0].split('/')[-1]
                _kl = len((locals().get('api_key') or '').strip())
                if _b or _u: e = Exception(f'{e} [{_u} | key={_kl}] {_b}')
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
        _b = e.read().decode('utf-8', errors='ignore')[:260] if hasattr(e, 'read') else ''
        _u = locals().get('url', '').split('?')[0].split('/')[-1]
        _kl = len((locals().get('api_key') or '').strip())
        if _b or _u: e = Exception(f'{e} [{_u} | key={_kl}] {_b}')
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

    estudiantes_qs = EstudiantePerfil.objects.select_related("curso", "user").order_by(
        "curso__nombre", "user__last_name", "apellidos_nombres"
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