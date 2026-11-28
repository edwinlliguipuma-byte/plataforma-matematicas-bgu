import re
import json
import unicodedata
from .models import Evaluacion, ModuloInteractivo


def _limpiar_titulo_comparacion(titulo):
    txt = (titulo or "").strip()
    txt = re.sub(r"^\[(?:m[o?]dulo\s*ia|eis|evaluaci[o?]n\s*ia)\]\s*", "", txt, flags=re.IGNORECASE)
    txt = "".join(
        c for c in unicodedata.normalize("NFD", txt.upper()) if unicodedata.category(c) != "Mn"
    )
    return " ".join(txt.split())


def _detectar_esp_par(nombre_curso):
    texto = (nombre_curso or "").lower()
    esp = "Inform?tica"
    if "contab" in texto:
        esp = "Contabilidad"
    elif "inform" in texto:
        esp = "Inform?tica"
    elif "venta" in texto:
        esp = "Ventas"
    elif "agrop" in texto:
        esp = "Agropecuaria"

    par = "A"
    for letra in ("A", "B", "C"):
        if f"'{letra.lower()}'" in texto or f'"{letra.lower()}"' in texto or texto.endswith(f" {letra.lower()}"):
            par = letra
            break
    return esp, par


def migrar_evaluaciones_sin_sobrescribir():
    """
    Env?a a ModuloInteractivo todo registro de Evaluacion que a?n no exista all?,
    sin duplicar ni sobrescribir ning?n m?dulo IA existente.
    """
    existentes_por_vinculo = set(
        ModuloInteractivo.objects.exclude(evaluacion_vinculada__isnull=True)
        .values_list("evaluacion_vinculada_id", flat=True)
    )

    mapa_existentes = {}
    for mod in ModuloInteractivo.objects.select_related("curso").all():
        clave = (mod.curso_id, _limpiar_titulo_comparacion(mod.titulo))
        if clave not in mapa_existentes:
            mapa_existentes[clave] = mod

    creados = 0
    for ev in Evaluacion.objects.select_related("curso").all().order_by("id"):
        if ev.id in existentes_por_vinculo:
            continue

        clave_ev = (ev.curso_id, _limpiar_titulo_comparacion(ev.titulo))
        if clave_ev in mapa_existentes:
            # Ya existe en M?dulos IA: NO sobrescribir; solo vincular si estaba suelto
            mod_existente = mapa_existentes[clave_ev]
            if mod_existente.evaluacion_vinculada_id is None:
                mod_existente.evaluacion_vinculada = ev
                mod_existente.save(update_fields=["evaluacion_vinculada"])
            continue

        titulo_limpio = re.sub(
            r"^\[(?:m[o?]dulo\s*ia|eis|evaluaci[o?]n\s*ia)\]\s*",
            "",
            (ev.titulo or "").strip(),
            flags=re.IGNORECASE,
        ).strip() or (ev.titulo or "M?dulo Acad?mico")

        desc = (ev.descripcion or "").strip()
        url_ext = (ev.enlace_externo or "").strip()
        if not url_ext and desc:
            m_url = re.search(r"https?://\S+", desc)
            if m_url:
                url_ext = m_url.group(0).rstrip(".,;)")

        esp, par = _detectar_esp_par(ev.curso.nombre if ev.curso else "")
        contenido_legacy = {
            "es_migrado_externo": True,
            "subtitulo": titulo_limpio,
            "instrucciones": desc,
            "enlace_externo": url_ext,
            "notacion_general": "",
            "anatomia_pasos": [],
            "tarjetas_infografia": [],
            "tarea_guiada": [],
            "deber_casa": [],
            "evaluacion_20": [],
        }

        nuevo_mod = ModuloInteractivo.objects.create(
            titulo=titulo_limpio[:200],
            asignatura="Matem?tica",
            curso=ev.curso,
            especialidad=esp,
            paralelo=par,
            destreza_indicadores=desc,
            tiempo_minutos=30,
            contenido_json=json.dumps(contenido_legacy, ensure_ascii=False),
            evaluacion_vinculada=ev,
        )
        mapa_existentes[clave_ev] = nuevo_mod
        creados += 1

    return creados
