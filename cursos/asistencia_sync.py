import json
from datetime import date
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from .models import Curso, Estudiante, Asistencia


@login_required
def vista_asistencia_offline(request):
    cursos = Curso.objects.all().order_by("id")
    datos_cursos = []

    for curso in cursos:
        estudiantes = (
            Estudiante.objects.filter(curso=curso).order_by("apellidos", "nombres")
            if hasattr(Estudiante, "apellidos")
            else Estudiante.objects.filter(curso=curso).order_by("id")
        )
        lista_est = []
        for est in estudiantes:
            nombre_completo = (
                f"{est.apellidos} {est.nombres}".strip()
                if hasattr(est, "apellidos") and hasattr(est, "nombres")
                else str(est)
            )
            lista_est.append({
                "id": est.id,
                "nombre": nombre_completo,
            })

        datos_cursos.append({
            "id": curso.id,
            "nombre": str(curso),
            "estudiantes": lista_est,
        })

    context = {
        "cursos_json": json.dumps(datos_cursos, ensure_ascii=False),
        "hoy": date.today().isoformat(),
    }
    return render(request, "cursos/asistencia_offline.html", context)


@login_required
@require_POST
def api_sincronizar_asistencia(request):
    try:
        payload = json.loads(request.body)
        registros = payload.get("registros", [])
        sincronizados = 0

        for item in registros:
            curso = Curso.objects.get(id=item["curso_id"])
            estudiante = Estudiante.objects.get(id=item["estudiante_id"], curso=curso)

            Asistencia.objects.update_or_create(
                curso=curso,
                estudiante=estudiante,
                fecha=item["fecha"],
                defaults={
                    "estado": item["estado"],
                    "observacion": item.get("observacion", ""),
                },
            )
            sincronizados += 1

        return JsonResponse({"ok": True, "sincronizados": sincronizados})
    except Curso.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Uno de los cursos no existe en la base de datos."}, status=404)
    except Estudiante.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Uno de los estudiantes no corresponde al curso."}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
