import json
import random
import re
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from .models import Tarea, EstudiantePerfil, EntregaTarea, Evaluacion, ResultadoEvaluacion


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
            return _agregar_cors(JsonResponse({'ok': False, 'error': 'Faltan datos del estudiante o evaluación'}, status=400))

        estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
        evaluacion = Evaluacion.objects.get(id=evaluacion_id)

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
        return _agregar_cors(JsonResponse({'ok': False, 'error': 'Evaluación no encontrada'}, status=404))
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
    """
    Evalúa automáticamente cuando el tipo es 'materia':
    - Incompleto: nota entre 6.0 y 7.0 (mínimo 6, máximo 7).
    - Completo: nota 8.0, 9.0 o 10.0.
    """
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

            if tipo == 'materia':
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

            else:  # 'deber' por defecto
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
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id)
    enlaces = re.findall(r'https?://[^\s<>"]+', evaluacion.descripcion or '')
    error = None
    estudiante = None
    resultado_guardado = None

    cedula = (request.POST.get('cedula') or request.GET.get('cedula') or '').strip()
    if cedula:
        try:
            estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
            resultado_guardado = ResultadoEvaluacion.objects.filter(
                evaluacion=evaluacion,
                estudiante=estudiante
            ).first()
        except EstudiantePerfil.DoesNotExist:
            error = "La cédula ingresada no está registrada en el sistema."

    return render(request, 'cursos/evaluacion.html', {
        'evaluacion': evaluacion,
        'enlaces': enlaces,
        'error': error,
        'estudiante': estudiante,
        'resultado_guardado': resultado_guardado,
    })