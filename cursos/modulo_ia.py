import os
import io
import csv
import json
import base64
import urllib.request
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


@staff_member_required
def panel_docente_institucional(request):
    cursos = CursoBGU.objects.all().order_by("nombre")
    curso_id = request.GET.get("curso_id", "")
    exportar = request.GET.get("exportar", "")

    estudiantes_qs = EstudiantePerfil.objects.select_related("curso", "user").order_by(
        "curso__nombre", "user__last_name", "apellidos_nombres"
    )
    if curso_id:
        estudiantes_qs = estudiantes_qs.filter(curso_id=curso_id)

    filas = []
    total_con_pendientes = 0

    for est in estudiantes_qs:
        prom_materia = (
            EntregaTarea.objects.filter(estudiante=est, tarea__tipo_tarea="MATERIA").aggregate(
                p=Avg("nota_calculada")
            )["p"]
            or 0
        )
        prom_deberes = (
            EntregaTarea.objects.filter(estudiante=est, tarea__tipo_tarea="DEBER").aggregate(
                p=Avg("nota_calculada")
            )["p"]
            or 0
        )
        prom_talleres = (
            EntregaTarea.objects.filter(estudiante=est, tarea__tipo_tarea="TALLER").aggregate(
                p=Avg("nota_calculada")
            )["p"]
            or 0
        )
        prom_evals = (
            ResultadoEvaluacion.objects.filter(estudiante=est).aggregate(p=Avg("nota_obtenida"))[
                "p"
            ]
            or 0
        )

        notas_activas = [
            float(n) for n in [prom_materia, prom_deberes, prom_talleres, prom_evals] if n > 0
        ]
        promedio_final = round(sum(notas_activas) / len(notas_activas), 2) if notas_activas else 0.0

        tareas_total = Tarea.objects.filter(curso=est.curso).count()
        tareas_ok = (
            EntregaTarea.objects.filter(estudiante=est, nota_calculada__gte=7)
            .values("tarea_id")
            .distinct()
            .count()
        )
        evals_total = Evaluacion.objects.filter(curso=est.curso).count()
        evals_ok = (
            ResultadoEvaluacion.objects.filter(estudiante=est, nota_obtenida__gte=7)
            .values("evaluacion_id")
            .distinct()
            .count()
        )
        pendientes = max(0, (tareas_total - tareas_ok) + (evals_total - evals_ok))
        if pendientes > 0:
            total_con_pendientes += 1

        filas.append(
            {
                "estudiante": est,
                "materia": round(float(prom_materia), 2),
                "deberes": round(float(prom_deberes), 2),
                "talleres": round(float(prom_talleres), 2),
                "evaluaciones": round(float(prom_evals), 2),
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

    return render(
        request,
        "cursos/panel_docente.html",
        {
            "cursos": cursos,
            "curso_id_actual": curso_id,
            "filas": filas,
            "total_estudiantes": len(filas),
            "total_modulos": ModuloInteractivo.objects.count(),
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
        titulo = request.POST.get("titulo", "").strip()
        asignatura = request.POST.get("asignatura", "Matemática Aplicada").strip()
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

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)

                evaluacion = Evaluacion.objects.create(
                    titulo=f"[Módulo IA] {titulo}",
                    curso=curso,
                )
                tarea_obj = Tarea.objects.filter(id=tarea_id).first() if tarea_id else None

                modulo = ModuloInteractivo.objects.create(
                    titulo=titulo,
                    asignatura=asignatura,
                    institucion=institucion,
                    curso=curso,
                    especialidad=especialidad,
                    paralelo=paralelo,
                    destreza_indicadores=destreza,
                    tiempo_minutos=tiempo_minutos,
                    contenido_json=json.dumps(parsed, ensure_ascii=False),
                    evaluacion_vinculada=evaluacion,
                    tarea_deber_vinculada=tarea_obj,
                )
                return redirect("ver_modulo_interactivo", modulo_id=modulo.id)
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
    cursos = CursoBGU.objects.all().order_by("nombre")
    curso_id = request.GET.get("curso_id", "")

    if request.method == "POST":
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

    reporte = []
    for est in estudiantes_qs:
        tareas_curso = Tarea.objects.filter(curso=est.curso)
        evals_curso = Evaluacion.objects.filter(curso=est.curso)

        entregas_ids = set(
            EntregaTarea.objects.filter(estudiante=est, nota_calculada__gte=7).values_list(
                "tarea_id", flat=True
            )
        )
        evals_ids = set(
            ResultadoEvaluacion.objects.filter(estudiante=est, nota_obtenida__gte=7).values_list(
                "evaluacion_id", flat=True
            )
        )

        pendientes = []
        for t in tareas_curso:
            if t.id not in entregas_ids:
                ent = EntregaTarea.objects.filter(estudiante=est, tarea=t).first()
                estado_txt = f"Nota baja ({ent.nota_calculada}/10)" if ent else "Sin entregar"
                pendientes.append(f"[{t.get_tipo_tarea_display()}] {t.titulo} ({estado_txt})")

        for ev in evals_curso:
            if ev.id not in evals_ids:
                res = ResultadoEvaluacion.objects.filter(estudiante=est, evaluacion=ev).first()
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