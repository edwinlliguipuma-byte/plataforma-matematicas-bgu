import base64
import csv
import json
import os
import re
import unicodedata
import urllib.request
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from .models import (
    MuestraSelloFirma,
    CursoBGU,
    Tarea,
    EstudiantePerfil,
    EntregaTarea,
    Evaluacion,
    ResultadoEvaluacion,
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

def _agregar_cors(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def _clave_alfabetica(estudiante):
    texto = (estudiante.nombre_completo or '').strip().upper()
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )


def _detectar_mime(archivo):
    content_type = getattr(archivo, 'content_type', '') or ''
    if content_type.startswith('image/') or content_type == 'application/pdf':
        return content_type
    nombre = (archivo.name or '').lower()
    if nombre.endswith('.pdf'):
        return 'application/pdf'
    if nombre.endswith('.png'):
        return 'image/png'
    if nombre.endswith('.webp'):
        return 'image/webp'
    return 'image/jpeg'


def calificar_cuaderno_con_gemini(tarea, archivos):
    """
    Analiza las imágenes o PDF subidos por el estudiante usando Gemini Vision:
    - Si es 'materia': verifica carátula, presentación y completitud (nota entre 6.00 y 10.00).
    - Si es 'deber' o 'taller': envía primero las muestras oficiales del sello y firma del docente
      para compararlas con las hojas del estudiante, cuenta sellos/firmas completos (1 pt)
      y atrasados marcados con 'A' (0.5 pts), y calcula el promedio sobre 10.
    """
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    tipo = (tarea.tipo_tarea or '').lower().strip()

    if not api_key:
        return {
            'nota': 8.0 if tipo == 'materia' else 7.0,
            'estado_materia': 'completo' if tipo == 'materia' else None,
            'sellos_completos': 0,
            'sellos_atrasados': 0,
            'observacion': 'Archivo recibido correctamente (Falta configurar GEMINI_API_KEY en Render para habilitar la revisión automática con IA).'
        }

    partes = []

    if tipo == 'materia':
        for f in archivos:
            f.seek(0)
            raw_bytes = f.read()
            f.seek(0)
            partes.append({
                'inline_data': {
                    'mime_type': _detectar_mime(f),
                    'data': base64.b64encode(raw_bytes).decode('utf-8')
                }
            })

        prompt = (
            f"Eres un docente de Matemática de Bachillerato Técnico en Ecuador revisando el cuaderno de MATERIA.\n"
            f"Título de la actividad: '{tarea.titulo}'.\n"
            f"Temas/Instrucciones esperadas: '{tarea.descripcion}'.\n\n"
            "Analiza todas las páginas (imágenes o PDF) adjuntas siguiendo estas reglas estrictas:\n"
            "1. Verifica si tiene CARÁTULA al inicio.\n"
            "2. Evalúa la PRESENTACIÓN (orden, limpieza, caligrafía legible, títulos subrayados).\n"
            "3. Verifica si la MATERIA está COMPLETA acorde a los temas solicitados.\n"
            "4. Asigna una NOTA numérica entre 6.00 (mínimo absoluto, incluso si está incompleta o sin carátula) y 10.00 (si tiene carátula, excelente presentación y materia completa). "
            "Si falta carátula o está incompleta, asigna entre 6.00 y 7.90 según el avance.\n\n"
            "Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:\n"
            '{"tiene_caratula": true, "estado_materia": "completo", "nota": 9.5, "observacion": "Explicación breve en español para el estudiante"}'
        )
        partes.append({'text': prompt})

    else:
        muestras = list(MuestraSelloFirma.objects.filter(activo=True))
        descripciones_muestras = []
        tiene_imagenes_ref = False

        if muestras:
            partes.append({
                'text': "=== PATRÓN OFICIAL DEL DOCENTE (SELLO Y/O FIRMA AUTÉNTICOS) ===\n"
                        "Observa cuidadosamente las siguientes imágenes de referencia del sello y firma del docente:"
            })
            for m in muestras:
                if m.descripcion_visual:
                    descripciones_muestras.append(m.descripcion_visual.strip())
                if m.sello_base64:
                    tiene_imagenes_ref = True
                    partes.append({'text': f"Muestra de SELLO OFICIAL ({m.nombre}):"})
                    partes.append({
                        'inline_data': {
                            'mime_type': m.sello_mime or 'image/jpeg',
                            'data': m.sello_base64
                        }
                    })
                if m.firma_base64:
                    tiene_imagenes_ref = True
                    partes.append({'text': f"Muestra de FIRMA A MANO DEL DOCENTE ({m.nombre}):"})
                    partes.append({
                        'inline_data': {
                            'mime_type': m.firma_mime or 'image/jpeg',
                            'data': m.firma_base64
                        }
                    })

        partes.append({
            'text': "=== PÁGINAS DEL CUADERNO DEL ESTUDIANTE A CALIFICAR ==="
        })
        for f in archivos:
            f.seek(0)
            raw_bytes = f.read()
            f.seek(0)
            partes.append({
                'inline_data': {
                    'mime_type': _detectar_mime(f),
                    'data': base64.b64encode(raw_bytes).decode('utf-8')
                }
            })

        regla_comparacion = (
            "IMPORTANTE: Compara visualmente cada sello o firma encontrado en el cuaderno del estudiante contra las IMÁGENES DE REFERENCIA OFICIAL DEL DOCENTE mostradas al inicio. "
            "Cuenta ÚNICAMENTE los sellos o firmas que coincidan con el patrón del docente e ignora firmas de representantes o marcas ajenas.\n"
            if tiene_imagenes_ref else
            "Cuenta los sellos docentes o firmas de revisión hechos por el profesor en las páginas del estudiante.\n"
        )
        texto_desc_docente = (
            f"Descripción adicional del docente sobre su sello/firma: {' | '.join(descripciones_muestras)}\n"
            if descripciones_muestras else ""
        )

        prompt = (
            f"Eres un docente de Matemática de Bachillerato Técnico en Ecuador revisando evidencias de {tipo.upper()}.\n"
            f"Título de la actividad: '{tarea.titulo}'.\n"
            f"Total de sellos o firmas esperados en esta actividad: {tarea.total_sellos_esperados}.\n"
            f"{texto_desc_docente}"
            f"{regla_comparacion}\n"
            "Clasifica cada sello/firma auténtico del docente encontrado en las hojas del estudiante:\n"
            "1. 'sellos_completos': cantidad de sellos/firmas del docente que NO tienen marca de atraso (valen 1.0 punto cada uno).\n"
            "2. 'sellos_atrasados': cantidad de sellos/firmas del docente que tienen escrita a mano la letra 'A' (atrasado) junto al sello o firma (valen la mitad: 0.5 puntos cada uno).\n"
            "No cuentes dos veces el mismo sello en páginas repetidas.\n\n"
            "Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:\n"
            '{"sellos_completos": 0, "sellos_atrasados": 0, "observacion": "Detalle claro en español indicando cuántos sellos/firmas completos y cuántos atrasados (A) se identificaron"}'
        )
        partes.append({'text': prompt})

    payload = {
        'contents': [{'parts': partes}],
        'generationConfig': {
            'temperature': 0.1,
            'responseMimeType': 'application/json'
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            texto_respuesta = body['candidates'][0]['content']['parts'][0]['text'].strip()
            texto_respuesta = re.sub(r'^```json\s*|\s*```$', '', texto_respuesta).strip()
            resultado = json.loads(texto_respuesta)

            if tipo == 'materia':
                nota_raw = float(resultado.get('nota', 7.0))
                nota_final = round(max(6.0, min(10.0, nota_raw)), 2)
                estado_mat = str(resultado.get('estado_materia', 'completo')).lower()
                if estado_mat not in ('completo', 'incompleto'):
                    estado_mat = 'completo' if nota_final >= 8.0 else 'incompleto'
                tiene_car = "Sí" if resultado.get('tiene_caratula') else "No detectada"
                obs = f"[Carátula: {tiene_car}] {resultado.get('observacion', '')}".strip()
                return {
                    'nota': nota_final,
                    'estado_materia': estado_mat,
                    'sellos_completos': 0,
                    'sellos_atrasados': 0,
                    'observacion': obs,
                }
            else:
                completos = max(0, int(resultado.get('sellos_completos', 0)))
                atrasados = max(0, int(resultado.get('sellos_atrasados', 0)))
                puntaje_total = completos * 1.0 + atrasados * 0.5
                esperados = max(1, int(tarea.total_sellos_esperados or 10))
                nota_final = round(min(10.0, (puntaje_total / esperados) * 10.0), 2)
                obs = (
                    f"Completos: {completos} (={completos * 1.0:.1f} pts) | "
                    f"Atrasados 'A': {atrasados} (={atrasados * 0.5:.1f} pts) | "
                    f"Total: {puntaje_total:.1f} / {esperados} esperados. "
                    f"{resultado.get('observacion', '')}"
                ).strip()
                return {
                    'nota': nota_final,
                    'estado_materia': None,
                    'sellos_completos': completos,
                    'sellos_atrasados': atrasados,
                    'observacion': obs,
                }

    except Exception as e:
        return {
            'nota': 6.0 if tipo == 'materia' else 0.0,
            'estado_materia': 'incompleto' if tipo == 'materia' else None,
            'sellos_completos': 0,
            'sellos_atrasados': 0,
            'observacion': f"Archivo recibido, pero ocurrió un inconveniente al analizar con IA ({str(e)[:120]}). El docente revisará el archivo manualmente.",
        }


@csrf_exempt
def api_guardar_nota_evaluacion(request):
    if request.method == 'OPTIONS':
        return _agregar_cors(JsonResponse({'ok': True}))

    if request.method != 'POST':
        return _agregar_cors(JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405))

    try:
        datos = json.loads(request.body.decode('utf-8'))
        cedula = str(datos.get('cedula', '')).strip()
        evaluacion_id = datos.get('evaluacion_id')
        nota = float(str(datos.get('nota', 0)).replace(',', '.'))
        nota = round(max(0.0, min(10.0, nota)), 2)

        if not cedula or not evaluacion_id:
            return _agregar_cors(JsonResponse({'ok': False, 'error': 'Faltan datos del estudiante o módulo'}, status=400))

        estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
        evaluacion = Evaluacion.objects.select_related('curso').get(id=evaluacion_id)

        if estudiante.curso_id != evaluacion.curso_id:
            return _agregar_cors(JsonResponse({
                'ok': False,
                'error': f'Acceso denegado: este módulo es de {evaluacion.curso.nombre}, pero estás registrado en {estudiante.curso.nombre}.'
            }, status=403))

        ResultadoEvaluacion.objects.update_or_create(
            evaluacion=evaluacion,
            estudiante=estudiante,
            defaults={'nota_obtenida': nota}
        )

        return _agregar_cors(JsonResponse({
            'ok': True,
            'estudiante': estudiante.nombre_completo,
            'nota': nota,
        }))
    except EstudiantePerfil.DoesNotExist:
        return _agregar_cors(JsonResponse({'ok': False, 'error': 'Cédula no encontrada en la plataforma'}, status=404))
    except Evaluacion.DoesNotExist:
        return _agregar_cors(JsonResponse({'ok': False, 'error': 'Módulo no encontrado'}, status=404))
    except Exception as e:
        return _agregar_cors(JsonResponse({'ok': False, 'error': str(e)}, status=400))


def buscar_estudiante_json(request, cedula):
    cedula_limpia = (cedula or '').strip()
    try:
        estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula_limpia)
        return JsonResponse({
            'encontrado': True,
            'apellidos_nombres': estudiante.nombre_completo,
            'cedula': estudiante.cedula,
            'curso': estudiante.curso.nombre if estudiante.curso else '',
        })
    except EstudiantePerfil.DoesNotExist:
        return JsonResponse({'encontrado': False})


def subir_tarea(request, tarea_id):
    tarea = get_object_or_404(Tarea.objects.select_related('curso'), id=tarea_id)
    tipo = (tarea.tipo_tarea or '').lower().strip()
    error = None
    cedula_inicial = (request.POST.get('cedula') or request.GET.get('cedula') or '').strip()
    tiene_muestra_sello = MuestraSelloFirma.objects.filter(activo=True).exists()

    if request.method == 'POST':
        _normalizar_curso_bgu_post(request)
        cedula = cedula_inicial
        archivos = request.FILES.getlist('archivos_estudiante')
        if not archivos and request.FILES.get('archivo_estudiante'):
            archivos = [request.FILES.get('archivo_estudiante')]

        try:
            estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)

            if estudiante.curso_id != tarea.curso_id:
                error = f"Esta actividad pertenece a {tarea.curso.nombre}, pero tu cédula está registrada en {estudiante.curso.nombre}."
            elif not archivos:
                error = "Debes subir al menos una imagen o un archivo PDF de tu cuaderno."
            else:
                analisis = calificar_cuaderno_con_gemini(tarea, archivos)
                nota = analisis['nota']
                estado_materia = analisis['estado_materia']
                sellos_completos = analisis['sellos_completos']
                sellos_atrasados = analisis['sellos_atrasados']
                observacion_ia = analisis['observacion']

                sellos_deb = sellos_completos if tipo == 'deber' else 0
                sellos_tall = sellos_completos if tipo == 'taller' else 0

                archivo_principal = archivos[0]
                archivo_principal.seek(0)

                EntregaTarea.objects.update_or_create(
                    tarea=tarea,
                    estudiante=estudiante,
                    defaults={
                        'archivo_estudiante': archivo_principal,
                        'estado_materia': estado_materia,
                        'sellos_deberes': sellos_deb,
                        'sellos_talleres': sellos_tall,
                        'sellos_atrasados': sellos_atrasados,
                        'nota_calculada': nota,
                        'observacion_ia': observacion_ia,
                    }
                )
                return render(request, 'cursos/tarea_exitosa.html', {
                    'tarea': tarea,
                    'tipo_tarea': tipo,
                    'estudiante': estudiante,
                    'nota': nota,
                    'estado_materia': estado_materia,
                    'sellos_deberes': sellos_deb,
                    'sellos_talleres': sellos_tall,
                    'sellos_atrasados': sellos_atrasados,
                    'observacion_ia': observacion_ia,
                    'total_archivos': len(archivos),
                })

        except EstudiantePerfil.DoesNotExist:
            error = "La cédula ingresada no está registrada en el sistema."

    return render(request, 'cursos/subir_tarea.html', {
        'tarea': tarea,
        'tipo_tarea': tipo,
        'error': error,
        'cedula_inicial': cedula_inicial,
        'tiene_muestra_sello': tiene_muestra_sello,
    })


def ver_evaluacion(request, evaluacion_id):
    evaluacion = get_object_or_404(Evaluacion.objects.select_related('curso'), id=evaluacion_id)
    enlaces = re.findall(r'https?://[^\s<>"]+', evaluacion.descripcion or '')
    error = None
    estudiante = None
    resultado_guardado = None
    curso_incorrecto = False
    modulos_su_curso = []

    cedula = (request.POST.get('cedula') or request.GET.get('cedula') or '').strip()
    if cedula:
        try:
            estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
            if estudiante.curso_id != evaluacion.curso_id:
                curso_incorrecto = True
                modulos_su_curso = Evaluacion.objects.filter(curso=estudiante.curso).order_by('-fecha_creacion')
            else:
                resultado_guardado = ResultadoEvaluacion.objects.filter(
                    evaluacion=evaluacion,
                    estudiante=estudiante
                ).first()
        except EstudiantePerfil.DoesNotExist:
            error = "La cédula ingresada no está registrada en el sistema. Verifica que no tenga espacios ni guiones."

    return render(request, 'cursos/evaluacion.html', {
        'evaluacion': evaluacion,
        'enlaces': enlaces,
        'error': error,
        'estudiante': estudiante,
        'resultado_guardado': resultado_guardado,
        'curso_incorrecto': curso_incorrecto,
        'modulos_su_curso': modulos_su_curso,
    })


def portal_estudiante(request):
    error = None
    estudiante = None
    modulos_con_nota = []
    tareas_con_nota = []

    cedula = (request.POST.get('cedula') or request.GET.get('cedula') or '').strip()
    if cedula:
        try:
            estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
            modulos = Evaluacion.objects.filter(curso=estudiante.curso).order_by('-fecha_creacion')
            resultados_map = {
                r.evaluacion_id: r
                for r in ResultadoEvaluacion.objects.filter(estudiante=estudiante, evaluacion__in=modulos)
            }
            for mod in modulos:
                modulos_con_nota.append({
                    'modulo': mod,
                    'resultado': resultados_map.get(mod.id),
                })

            tareas = Tarea.objects.filter(curso=estudiante.curso).order_by('-fecha_limite')
            entregas_map = {
                e.tarea_id: e
                for e in EntregaTarea.objects.filter(estudiante=estudiante, tarea__in=tareas)
            }
            for t in tareas:
                tareas_con_nota.append({
                    'tarea': t,
                    'entrega': entregas_map.get(t.id),
                })
        except EstudiantePerfil.DoesNotExist:
            error = "La cédula ingresada no está registrada en la plataforma."

    return render(request, 'cursos/portal_estudiante.html', {
        'error': error,
        'estudiante': estudiante,
        'modulos_con_nota': modulos_con_nota,
        'tareas_con_nota': tareas_con_nota,
    })


@staff_member_required(login_url='/admin/login/')
def panel_docente(request):
    vista = request.GET.get('vista', 'lecciones').strip()
    if vista not in ('lecciones', 'tareas'):
        vista = 'lecciones'

    cursos = CursoBGU.objects.all().order_by('nombre')
    curso_id = request.GET.get('curso', '').strip()
    evaluacion_id = request.GET.get('evaluacion', '').strip()
    tarea_id = request.GET.get('tarea', '').strip()
    estado_filtro = request.GET.get('estado', 'todos').strip()
    muestra_activa = MuestraSelloFirma.objects.filter(activo=True).first()

    curso_seleccionado = None
    if curso_id.isdigit():
        curso_seleccionado = CursoBGU.objects.filter(id=int(curso_id)).first()

    if vista == 'tareas':
        if curso_seleccionado:
            tareas_disponibles = Tarea.objects.select_related('curso').filter(curso=curso_seleccionado).order_by('-fecha_limite')
        else:
            tareas_disponibles = Tarea.objects.select_related('curso').all().order_by('-fecha_limite')

        tarea_seleccionada = None
        if tarea_id.isdigit():
            tarea_seleccionada = tareas_disponibles.filter(id=int(tarea_id)).first()
        if not tarea_seleccionada and tareas_disponibles.exists():
            tarea_seleccionada = tareas_disponibles.first()

        curso_activo = tarea_seleccionada.curso if tarea_seleccionada else curso_seleccionado
        filas = []

        if curso_activo:
            estudiantes_qs = EstudiantePerfil.objects.select_related('user', 'curso').filter(curso=curso_activo)
            estudiantes_ordenados = sorted(estudiantes_qs, key=_clave_alfabetica)

            entregas_map = {}
            if tarea_seleccionada:
                entregas_map = {
                    e.estudiante_id: e
                    for e in EntregaTarea.objects.filter(tarea=tarea_seleccionada)
                }

            for est in estudiantes_ordenados:
                ent = entregas_map.get(est.id)
                nota = ent.nota_calculada if ent else None
                fecha = ent.fecha_envio if ent else None

                if estado_filtro == 'rendidos' and nota is None:
                    continue
                if estado_filtro == 'pendientes' and nota is not None:
                    continue
                if estado_filtro == 'aprobados' and (nota is None or nota < 7.0):
                    continue
                if estado_filtro == 'refuerzo' and (nota is None or nota >= 7.0):
                    continue

                completos = 0
                if ent:
                    completos = ent.sellos_talleres if tarea_seleccionada.tipo_tarea == 'taller' else ent.sellos_deberes

                filas.append({
                    'estudiante': est,
                    'nota': nota,
                    'fecha': fecha,
                    'entrega': ent,
                    'sellos_completos': completos,
                    'sellos_atrasados': ent.sellos_atrasados if ent else 0,
                    'observacion_ia': ent.observacion_ia if ent else '',
                })

        total_nomina = len(filas)
        notas_validas = [f['nota'] for f in filas if f['nota'] is not None]
        total_rendidos = len(notas_validas)
        total_pendientes = total_nomina - total_rendidos
        promedio = round(sum(notas_validas) / total_rendidos, 2) if total_rendidos > 0 else 0.0

        return render(request, 'cursos/panel_docente.html', {
            'vista': 'tareas',
            'muestra_activa': muestra_activa,
            'cursos': cursos,
            'curso_seleccionado': curso_seleccionado,
            'curso_activo': curso_activo,
            'tareas_disponibles': tareas_disponibles,
            'tarea_seleccionada': tarea_seleccionada,
            'modulos_disponibles': [],
            'modulo_seleccionado': None,
            'curso_id_actual': curso_id,
            'estado_filtro': estado_filtro,
            'filas': filas,
            'total_nomina': total_nomina,
            'total_rendidos': total_rendidos,
            'total_pendientes': total_pendientes,
            'promedio': promedio,
        })

    # VISTA POR DEFECTO: LECCIONES / MÓDULOS
    if curso_seleccionado:
        modulos_disponibles = Evaluacion.objects.select_related('curso').filter(
            curso=curso_seleccionado
        ).order_by('-fecha_creacion')
    else:
        modulos_disponibles = Evaluacion.objects.select_related('curso').all().order_by('-fecha_creacion')

    modulo_seleccionado = None
    if evaluacion_id.isdigit():
        modulo_seleccionado = modulos_disponibles.filter(id=int(evaluacion_id)).first()
    if not modulo_seleccionado and modulos_disponibles.exists():
        modulo_seleccionado = modulos_disponibles.first()

    curso_activo = modulo_seleccionado.curso if modulo_seleccionado else curso_seleccionado

    filas = []
    if curso_activo:
        estudiantes_qs = EstudiantePerfil.objects.select_related('user', 'curso').filter(
            curso=curso_activo
        )
        estudiantes_ordenados = sorted(estudiantes_qs, key=_clave_alfabetica)

        resultados_map = {}
        if modulo_seleccionado:
            resultados_map = {
                r.estudiante_id: r
                for r in ResultadoEvaluacion.objects.filter(evaluacion=modulo_seleccionado)
            }

        for est in estudiantes_ordenados:
            res = resultados_map.get(est.id)
            nota = res.nota_obtenida if res else None
            fecha = res.fecha_registro if res else None

            if estado_filtro == 'rendidos' and nota is None:
                continue
            if estado_filtro == 'pendientes' and nota is not None:
                continue
            if estado_filtro == 'aprobados' and (nota is None or nota < 7.0):
                continue
            if estado_filtro == 'refuerzo' and (nota is None or nota >= 7.0):
                continue

            filas.append({
                'estudiante': est,
                'modulo': modulo_seleccionado,
                'nota': nota,
                'fecha': fecha,
            })

    total_nomina = len(filas)
    notas_validas = [f['nota'] for f in filas if f['nota'] is not None]
    total_rendidos = len(notas_validas)
    total_pendientes = total_nomina - total_rendidos
    promedio = round(sum(notas_validas) / total_rendidos, 2) if total_rendidos > 0 else 0.0

    return render(request, 'cursos/panel_docente.html', {
        'vista': 'lecciones',
        'muestra_activa': muestra_activa,
        'cursos': cursos,
        'curso_seleccionado': curso_seleccionado,
        'curso_activo': curso_activo,
        'modulos_disponibles': modulos_disponibles,
        'modulo_seleccionado': modulo_seleccionado,
        'tareas_disponibles': [],
        'tarea_seleccionada': None,
        'curso_id_actual': curso_id,
        'estado_filtro': estado_filtro,
        'filas': filas,
        'total_nomina': total_nomina,
        'total_rendidos': total_rendidos,
        'total_pendientes': total_pendientes,
        'promedio': promedio,
    })


@staff_member_required(login_url='/admin/login/')
def exportar_notas_csv(request):
    vista = request.GET.get('vista', 'lecciones').strip()
    evaluacion_id = request.GET.get('evaluacion', '').strip()
    tarea_id = request.GET.get('tarea', '').strip()
    curso_id = request.GET.get('curso', '').strip()

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')

    if vista == 'tareas':
        tarea = Tarea.objects.select_related('curso').filter(id=int(tarea_id)).first() if tarea_id.isdigit() else None
        curso_activo = tarea.curso if tarea else (CursoBGU.objects.filter(id=int(curso_id)).first() if curso_id.isdigit() else None)

        nombre_archivo = f"Cuadernos_{curso_activo.nombre}_{tarea.titulo}.csv".replace(' ', '_').replace("'", "") if (curso_activo and tarea) else "Cuadernos_BGU.csv"
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'

        writer = csv.writer(response, delimiter=';')
        writer.writerow(['N°', 'Apellidos y Nombres', 'Cédula', 'Curso', 'Actividad', 'Sellos Completos (1pt)', 'Atrasados A (0.5pt)', 'Calificación (/10)', 'Estado', 'Detalle IA', 'Fecha Registro'])

        if curso_activo:
            estudiantes = sorted(
                EstudiantePerfil.objects.select_related('user', 'curso').filter(curso=curso_activo),
                key=_clave_alfabetica
            )
            entregas_map = {e.estudiante_id: e for e in EntregaTarea.objects.filter(tarea=tarea)} if tarea else {}

            for idx, est in enumerate(estudiantes, start=1):
                ent = entregas_map.get(est.id)
                if ent:
                    completos = ent.sellos_talleres if (tarea and tarea.tipo_tarea == 'taller') else ent.sellos_deberes
                    nota_str = f"{ent.nota_calculada:.2f}".replace('.', ',')
                    estado_str = "APROBADO" if ent.nota_calculada >= 7.0 else "REFUERZO"
                    fecha_str = ent.fecha_envio.strftime('%d/%m/%Y %H:%M')
                    writer.writerow([
                        idx, est.nombre_completo, est.cedula, est.curso.nombre,
                        tarea.titulo if tarea else "-", completos, ent.sellos_atrasados,
                        nota_str, estado_str, ent.observacion_ia or "", fecha_str
                    ])
                else:
                    writer.writerow([
                        idx, est.nombre_completo, est.cedula, est.curso.nombre,
                        tarea.titulo if tarea else "-", 0, 0, "0,00", "PENDIENTE", "", "-"
                    ])
        return response

    modulo = Evaluacion.objects.select_related('curso').filter(id=int(evaluacion_id)).first() if evaluacion_id.isdigit() else None
    curso_activo = modulo.curso if modulo else (CursoBGU.objects.filter(id=int(curso_id)).first() if curso_id.isdigit() else Evaluacion.objects.select_related('curso').order_by('-fecha_creacion').first().curso if Evaluacion.objects.exists() else None)

    if modulo:
        nombre_archivo = f"Calificaciones_{modulo.curso.nombre}_{modulo.titulo}.csv".replace(' ', '_').replace("'", "")
    elif curso_activo:
        nombre_archivo = f"Nomina_{curso_activo.nombre}.csv".replace(' ', '_').replace("'", "")
    else:
        nombre_archivo = "Calificaciones_BGU.csv"

    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['N°', 'Apellidos y Nombres', 'Cédula', 'Curso', 'Módulo / Lección', 'Calificación (/10)', 'Estado', 'Fecha y Hora de Registro'])

    if curso_activo:
        estudiantes = sorted(
            EstudiantePerfil.objects.select_related('user', 'curso').filter(curso=curso_activo),
            key=_clave_alfabetica
        )
        resultados_map = {r.estudiante_id: r for r in ResultadoEvaluacion.objects.filter(evaluacion=modulo)} if modulo else {}

        for idx, est in enumerate(estudiantes, start=1):
            res = resultados_map.get(est.id)
            if res:
                nota_str = f"{res.nota_obtenida:.2f}".replace('.', ',')
                estado_str = "APROBADO" if res.nota_obtenida >= 7.0 else "REFUERZO"
                fecha_str = res.fecha_registro.strftime('%d/%m/%Y %H:%M')
            else:
                nota_str = "0,00"
                estado_str = "PENDIENTE" if modulo else "SIN MÓDULO"
                fecha_str = "-"

            writer.writerow([
                idx,
                est.nombre_completo,
                est.cedula,
                est.curso.nombre,
                modulo.titulo if modulo else "Sin módulo asignado",
                nota_str,
                estado_str,
                fecha_str,
            ])

    return response