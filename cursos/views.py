import csv
import json
import random
import re
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from .models import CursoBGU, Tarea, EstudiantePerfil, EntregaTarea, Evaluacion, ResultadoEvaluacion


def _agregar_cors(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


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

        # Validación estricta: la nota solo se guarda si el estudiante pertenece al curso del módulo
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


def evaluar_materia_con_ia(estado_materia, archivo=None):
    if estado_materia == 'incompleto':
        return round(random.uniform(6.0, 7.0), 2)
    return float(random.choice([8, 9, 10]))


def subir_tarea(request, tarea_id):
    tarea = get_object_or_404(Tarea, id=tarea_id)
    tipo = (tarea.tipo_tarea or '').lower().strip()
    error = None

    if request.method == 'POST':
        cedula = request.POST.get('cedula', '').strip()
        archivo = request.FILES.get('archivo_estudiante')

        try:
            estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)

            if estudiante.curso_id != tarea.curso_id:
                error = f"Esta tarea pertenece a {tarea.curso.nombre}, pero tu cédula está registrada en {estudiante.curso.nombre}."
            elif tipo == 'materia':
                estado_materia = request.POST.get('estado_materia', '').strip().lower()
                if estado_materia not in ('completo', 'incompleto'):
                    error = "Selecciona si la materia está Completo o Incompleto."
                else:
                    sellos_deb = 0
                    sellos_tall = 0
                    nota = evaluar_materia_con_ia(estado_materia, archivo=archivo)
            elif tipo == 'taller':
                estado_materia = None
                sellos_deb = 0
                sellos_tall = max(0, int(request.POST.get('sellos_talleres', 0) or 0))
                nota = min(10.0, 5.0 + (sellos_tall * 0.5))
            else:
                estado_materia = None
                sellos_deb = max(0, int(request.POST.get('sellos_deberes', 0) or 0))
                sellos_tall = 0
                nota = min(10.0, 5.0 + (sellos_deb * 0.5))

            if not error:
                EntregaTarea.objects.update_or_create(
                    tarea=tarea,
                    estudiante=estudiante,
                    defaults={
                        'archivo_estudiante': archivo,
                        'estado_materia': estado_materia,
                        'sellos_deberes': sellos_deb,
                        'sellos_talleres': sellos_tall,
                        'nota_calculada': nota,
                    }
                )
                return render(request, 'cursos/tarea_exitosa.html', {
                    'tarea': tarea,
                    'estudiante': estudiante,
                    'nota': nota,
                    'estado_materia': estado_materia,
                    'sellos_deberes': sellos_deb,
                    'sellos_talleres': sellos_tall,
                })

        except EstudiantePerfil.DoesNotExist:
            error = "La cédula ingresada no está registrada en el sistema."

    return render(request, 'cursos/subir_tarea.html', {
        'tarea': tarea,
        'tipo_tarea': tipo,
        'error': error,
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
    """
    Portal único del estudiante (/aula/): al ingresar su cédula ve exclusivamente
    los Módulos de Clase y Lección y las Tareas de su propio curso.
    """
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
    """
    Panel exclusivo y responsivo para el docente (/docente/) con KPIs,
    filtros por curso/módulo, listado completo de estudiantes y descarga a Excel.
    """
    cursos = CursoBGU.objects.all().order_by('nombre')
    curso_id = request.GET.get('curso', '').strip()
    evaluacion_id = request.GET.get('evaluacion', '').strip()
    estado_filtro = request.GET.get('estado', 'todos').strip()

    if curso_id.isdigit():
        modulos_disponibles = Evaluacion.objects.filter(curso_id=int(curso_id)).order_by('-fecha_creacion')
    else:
        modulos_disponibles = Evaluacion.objects.select_related('curso').all().order_by('-fecha_creacion')

    modulo_seleccionado = None
    if evaluacion_id.isdigit():
        modulo_seleccionado = Evaluacion.objects.select_related('curso').filter(id=int(evaluacion_id)).first()
    elif modulos_disponibles.exists():
        modulo_seleccionado = modulos_disponibles.first()

    # Si hay un módulo seleccionado, mostramos la nómina completa del curso de ese módulo (rendidos + pendientes)
    filas = []
    if modulo_seleccionado:
        estudiantes_qs = EstudiantePerfil.objects.select_related('user', 'curso').filter(
            curso=modulo_seleccionado.curso
        ).order_by('apellidos_nombres', 'cedula')

        resultados_map = {
            r.estudiante_id: r
            for r in ResultadoEvaluacion.objects.filter(evaluacion=modulo_seleccionado)
        }

        for est in estudiantes_qs:
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
        'cursos': cursos,
        'modulos_disponibles': modulos_disponibles,
        'modulo_seleccionado': modulo_seleccionado,
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
    """
    Descarga las calificaciones filtradas en formato CSV compatible directamente con Excel.
    """
    evaluacion_id = request.GET.get('evaluacion', '').strip()
    modulo = None
    if evaluacion_id.isdigit():
        modulo = Evaluacion.objects.select_related('curso').filter(id=int(evaluacion_id)).first()
    if not modulo:
        modulo = Evaluacion.objects.select_related('curso').order_by('-fecha_creacion').first()

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    nombre_archivo = f"Calificaciones_{modulo.curso.nombre}_{modulo.titulo}.csv".replace(' ', '_').replace("'", "") if modulo else "Calificaciones_BGU.csv"
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['N°', 'Apellidos y Nombres', 'Cédula', 'Curso', 'Módulo / Lección', 'Calificación (/10)', 'Estado', 'Fecha y Hora de Registro'])

    if modulo:
        estudiantes = EstudiantePerfil.objects.select_related('user', 'curso').filter(
            curso=modulo.curso
        ).order_by('apellidos_nombres', 'cedula')
        resultados_map = {
            r.estudiante_id: r
            for r in ResultadoEvaluacion.objects.filter(evaluacion=modulo)
        }

        for idx, est in enumerate(estudiantes, start=1):
            res = resultados_map.get(est.id)
            if res:
                nota_str = f"{res.nota_obtenida:.2f}".replace('.', ',')
                estado_str = "APROBADO" if res.nota_obtenida >= 7.0 else "REFUERZO"
                fecha_str = res.fecha_registro.strftime('%d/%m/%Y %H:%M')
            else:
                nota_str = "0,00"
                estado_str = "PENDIENTE"
                fecha_str = "-"

            writer.writerow([
                idx,
                est.nombre_completo,
                est.cedula,
                est.curso.nombre,
                modulo.titulo,
                nota_str,
                estado_str,
                fecha_str,
            ])

    return response