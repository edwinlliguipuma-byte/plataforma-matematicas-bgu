import re, unicodedata
from django.db import migrations

def norm(txt):
    t = (txt or "").upper().strip()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")

def marcar_retirados(apps, schema_editor):
    EstudiantePerfil = apps.get_model("cursos", "EstudiantePerfil")
    for est in EstudiantePerfil.objects.select_related("curso").all():
        c = norm(est.curso.nombre if est.curso else "")
        n = norm(est.apellidos_nombres or (f"{est.user.last_name} {est.user.first_name}" if est.user else ""))
        es_2do = bool(re.search(r"\b(2DO|2°|SEGUNDO)\b", c))
        es_3ro = bool(re.search(r"\b(3RO|3ERO|3°|TERCERO)\b", c))
        es_cont = "CONT" in c
        par_a = bool(re.search(r"['\"\s]A(?:['\"\s]|$)", c))
        par_b = bool(re.search(r"['\"\s]B(?:['\"\s]|$)", c))

        marcar = False
        if es_2do and es_cont and par_a and "SANCHEZ" in n:
            marcar = True
        elif es_2do and es_cont and par_b and ("MALAN" in n or "MINIGUANO" in n):
            marcar = True
        elif es_3ro and es_cont and par_a and ("RODRIGUEZ" in n or "ULLOA" in n):
            marcar = True

        if marcar and not est.retirado:
            est.retirado = True
            est.save(update_fields=["retirado"])

class Migration(migrations.Migration):
    dependencies = [
        ("cursos", "0016_estudianteperfil_retirado"),
    ]
    operations = [
        migrations.RunPython(marcar_retirados, migrations.RunPython.noop),
    ]
