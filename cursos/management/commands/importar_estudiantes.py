import glob
import pandas as pd
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from cursos.models import CursoBGU, EstudiantePerfil


class Command(BaseCommand):
    help = 'Importa masivamente los estudiantes de forma instantánea'

    def handle(self, *args, **kwargs):
        mapeo_cursos = {
            "2DO DE BACHILLERATO, Técnico - Contabilidad A": "2do BGU Contabilidad 'A'",
            "2DO DE BACHILLERATO, Técnico - Contabilidad B": "2do BGU Contabilidad 'B'",
            "2DO DE BACHILLERATO, Técnico - Informática A": "2do BGU Informática 'A'",
            "2DO DE BACHILLERATO, Técnico - Informática B": "2do BGU Informática 'B'",
            "2DO DE BACHILLERATO, Técnico - Informática C": "2do BGU Informática 'C'",
            "3RO DE BACHILLERATO, Técnico - Contabilidad A": "3ro BGU Contabilidad 'A'",
            "3RO DE BACHILLERATO, Técnico - Contabilidad B": "3ro BGU Contabilidad 'B'",
            "3RO DE BACHILLERATO, Técnico - Informática A": "3ro BGU Informática 'A'",
            "3RO DE BACHILLERATO, Técnico - Informática B": "3ro BGU Informática 'B'",
            "3RO DE BACHILLERATO, Técnico - Informática C": "3ro BGU Informática 'C'",
        }

        archivos = glob.glob("*.csv")
        if not archivos:
            self.stdout.write(self.style.WARNING("No se encontraron archivos *.csv en la carpeta actual."))
            return

        total_importados = 0

        for archivo_csv in archivos:
            curso_db_nombre = None
            for clave, valor in mapeo_cursos.items():
                if clave in archivo_csv:
                    curso_db_nombre = valor
                    break

            if not curso_db_nombre:
                self.stdout.write(self.style.WARNING(f"Sin mapeo de curso para: {archivo_csv}"))
                continue

            curso_obj, _ = CursoBGU.objects.get_or_create(nombre=curso_db_nombre)

            df = pd.read_csv(archivo_csv)

            fila_inicio = None
            for idx, row in df.iterrows():
                row_str = str(row.values)
                if 'CÉDULA' in row_str or 'CEDULA' in row_str:
                    fila_inicio = idx + 1
                    break

            if fila_inicio is None:
                self.stdout.write(self.style.WARNING(f"No se encontró cabecera CÉDULA/CEDULA en: {archivo_csv}"))
                continue

            importados_archivo = 0
            for idx in range(fila_inicio, len(df)):
                row = df.iloc[idx]
                cedula = str(row.iloc[3]).strip()
                nombres_completos = str(row.iloc[5]).strip()
                correo = str(row.iloc[9]).strip()

                if not cedula or cedula.lower() == 'nan' or len(cedula) < 5:
                    continue

                partes = nombres_completos.split()
                if len(partes) >= 2:
                    apellidos = f"{partes[0]} {partes[1]}"
                    nombres = " ".join(partes[2:]) if len(partes) > 2 else partes[1]
                else:
                    apellidos = nombres_completos
                    nombres = "Estudiante"

                user, creado = User.objects.get_or_create(
                    username=cedula,
                    defaults={
                        'first_name': nombres,
                        'last_name': apellidos,
                        'email': correo if '@' in correo else f"{cedula}@estudiantes2.edu.ec"
                    }
                )
                if creado:
                    user.password = f"pbkdf2_sha256$600000$dummy$fastpass={cedula}"
                    user.save()

                perfil, _ = EstudiantePerfil.objects.get_or_create(
                    user=user,
                    defaults={'cedula': cedula, 'curso': curso_obj}
                )
                perfil.curso = curso_obj
                perfil.cedula = cedula
                perfil.save()

                total_importados += 1
                importados_archivo += 1

            self.stdout.write(f"  - {archivo_csv} -> {curso_db_nombre}: {importados_archivo} estudiantes")

        self.stdout.write(self.style.SUCCESS(f"¡EXITO_TOTAL: {total_importados} estudiantes importados perfectamente!"))