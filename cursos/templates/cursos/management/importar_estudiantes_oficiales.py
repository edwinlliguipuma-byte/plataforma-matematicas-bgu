import os
import glob
import pandas as pd
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from cursos.models import CursoBGU, EstudiantePerfil

class Command(BaseCommand):
    help = 'Importa masivamente los estudiantes de todos los archivos CSV de los 10 cursos'

    def handle(self, *args, **kwargs):
        # Mapeo de nombres de archivos CSV a los nombres exactos de los cursos en la Base de Datos
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

        total_importados = 0

        for archivo_csv in glob.glob("*.csv"):
            # Identificar a qué curso pertenece el archivo por su nombre
            curso_db_nombre = None
            for clave, valor in mapeo_cursos.items():
                if clave in archivo_csv:
                    curso_db_nombre = valor
                    break
            
            if not curso_db_nombre:
                self.stdout.write(self.style.WARNING(f"No se pudo mapear el archivo: {archivo_csv}"))
                continue

            try:
                curso_obj = CursoBGU.objects.get(nombre=curso_db_nombre)
            except CursoBGU.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"El curso '{curso_db_nombre}' no existe en la base de datos."))
                continue

            # Leer el CSV usando pandas (buscando la fila donde empieza la cédula)
            df = pd.read_csv(archivo_csv)
            
            # Buscamos la fila de inicio de datos
            fila_inicio = None
            for idx, row in df.iterrows():
                row_str = str(row.values)
                if 'CÉDULA' in row_str or 'CEDULA' in row_str:
                    fila_inicio = idx + 1
                    break

            if fila_inicio is None:
                self.stdout.write(self.style.WARNING(f"No se encontró la cabecera en {archivo_csv}"))
                continue

            # Procesamos las filas de estudiantes
            for idx in range(fila_inicio, len(df)):
                row = df.iloc[idx]
                cedula = str(row.iloc[3]).strip()
                nombres_completos = str(row.iloc[5]).strip()
                correo = str(row.iloc[9]).strip()

                # Validar que la cédula sea válida (ej. que no sea NaN o vacía)
                if not cedula or cedula.lower() == 'nan' or len(cedula) < 5:
                    continue

                # Dividir nombres y apellidos (aproximación: dos primeros nombres / dos apellidos)
                partes = nombres_completos.split()
                if len(partes) >= 2:
                    apellidos = f"{partes[0]} {partes[1]}"
                    nombres = " ".join(partes[2:]) if len(partes) > 2 else partes[1]
                else:
                    apellidos = nombres_completos
                    nombres = "Estudiante"

                # Verificar si el usuario ya existe
                if User.objects.filter(username=cedula).exists():
                    continue

                # Crear usuario de Django (cédula como username y contraseña inicial)
                user = User.objects.create_user(
                    username=cedula,
                    email=correo if '@' in correo else f"{cedula}@estudiantes2.edu.ec",
                    password=cedula,
                    first_name=nombres,
                    last_name=apellidos
                )

                # Crear perfil de estudiante vinculado al curso
                EstudiantePerfil.objects.create(
                    user=user,
                    curso=curso_obj,
                    cedula=cedula
                )
                total_importados += 1

        self.stdout.write(self.style.SUCCESS(f"¡Se importaron exitosamente {total_importados} estudiantes de todos los cursos!"))