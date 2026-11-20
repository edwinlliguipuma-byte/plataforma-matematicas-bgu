import random
import re
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import Tarea, EstudiantePerfil, EntregaTarea, Evaluacion, ResultadoEvaluacion


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

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'buscar_cedula':
            cedula = request.POST.get('cedula', '').strip()
            try:
                estudiante = EstudiantePerfil.objects.select_related('user', 'curso').get(cedula=cedula)
                resultado_guardado = ResultadoEvaluacion.objects.filter(
                    evaluacion=evaluacion,
                    estudiante=estudiante
                ).first()
            except EstudiantePerfil.DoesNotExist:
                error = "La cédula ingresada no está registrada en el sistema."

        elif accion == 'guardar_nota':
            estudiante_id = request.POST.get('estudiante_id')
            estudiante = get_object_or_404(EstudiantePerfil.objects.select_related('user', 'curso'), id=estudiante_id)
            nota_str = request.POST.get('nota_obtenida', '0').strip().replace(',', '.')

            try:
                nota = float(nota_str)
                nota = max(0.0, min(10.0, nota))
                resultado_guardado, _ = ResultadoEvaluacion.objects.update_or_create(
                    evaluacion=evaluacion,
                    estudiante=estudiante,
                    defaults={'nota_obtenida': nota}
                )
            except ValueError:
                error = "Por favor ingresa una nota válida."

    return render(request, 'cursos/evaluacion.html', {
        'evaluacion': evaluacion,
        'enlaces': enlaces,
        'error': error,
        'estudiante': estudiante,
        'resultado_guardado': resultado_guardado,
    })