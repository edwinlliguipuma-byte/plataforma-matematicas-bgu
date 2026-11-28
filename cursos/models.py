import io
import base64
from PIL import Image
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class MuestraSelloFirma(models.Model):
    nombre = models.CharField(
        max_length=150,
        default="Sello y Firma Oficial del Docente",
        verbose_name="Nombre Identificador",
    )
    imagen_sello = models.ImageField(
        upload_to="sellos/",
        blank=True,
        null=True,
        verbose_name="Foto del Sello Oficial",
    )
    imagen_firma = models.ImageField(
        upload_to="firmas/",
        blank=True,
        null=True,
        verbose_name="Foto de la Firma a Mano (y ejemplo de marca 'A' si deseas)",
    )
    sello_base64 = models.TextField(blank=True, null=True)
    sello_mime = models.CharField(max_length=50, blank=True, null=True)
    firma_base64 = models.TextField(blank=True, null=True)
    firma_mime = models.CharField(max_length=50, blank=True, null=True)
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descripción del Sello, Firma y Marca 'A'",
        help_text="Ej: Sello azul de la U.E. Dr. Enrique Noboa - Matemática y rúbrica con esfero azul. Cuando es atrasado escribo una letra 'A' junto al sello.",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo para Calificación IA")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Muestra de Sello y Firma"
        verbose_name_plural = "Muestras de Sello y Firma"

    def __str__(self):
        return self.nombre

    @staticmethod
    def _convertir_a_base64(campo_imagen):
        img = Image.open(campo_imagen)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if max(img.size) > 1024:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def save(self, *args, **kwargs):
        if self.imagen_sello:
            try:
                self.sello_base64 = self._convertir_a_base64(self.imagen_sello)
                self.sello_mime = "image/jpeg"
            except Exception:
                pass
        if self.imagen_firma:
            try:
                self.firma_base64 = self._convertir_a_base64(self.imagen_firma)
                self.firma_mime = "image/jpeg"
            except Exception:
                pass
        super().save(*args, **kwargs)


class CursoBGU(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Curso")

    class Meta:
        verbose_name = "Curso BGU"
        verbose_name_plural = "Cursos BGU"

    def __str__(self):
        return self.nombre


class EstudiantePerfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    apellidos_nombres = models.CharField(
        max_length=200, blank=True, null=True, verbose_name="Apellidos y Nombres"
    )
    cedula = models.CharField(max_length=20, unique=True, verbose_name="Número de Cédula")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    telefono_representante = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="Celular del Representante"
    )
    correo_representante = models.EmailField(
        blank=True, null=True, verbose_name="Correo del Representante"
    )
    retirado = models.BooleanField(
        default=False, verbose_name="Retirado (Estático)"
    )

    class Meta:
        verbose_name = "Estudiante"
        verbose_name_plural = "Estudiantes"

    @property
    def nombre_completo(self):
        if self.apellidos_nombres and self.apellidos_nombres.strip():
            return self.apellidos_nombres.strip()
        if self.user:
            completo = f"{self.user.last_name} {self.user.first_name}".strip()
            if completo:
                return completo
            return self.user.username
        return f"Estudiante {self.cedula}"

    def __str__(self):
        estado = " [RETIRADO]" if self.retirado else ""
        return f"{self.nombre_completo} ({self.cedula}){estado}"


class Tarea(models.Model):
    TIPO_CHOICES = [
        ("MATERIA", "Materia"),
        ("DEBER", "Deber"),
        ("TALLER", "Taller"),
    ]

    titulo = models.CharField(max_length=200, verbose_name="Título de la Tarea / Cuaderno")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Instrucciones")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    fecha_limite = models.DateTimeField(default=timezone.now, verbose_name="Fecha Límite")
    tipo_tarea = models.CharField(
        max_length=20, choices=TIPO_CHOICES, default="DEBER", verbose_name="Tipo"
    )
    total_sellos_esperados = models.PositiveIntegerField(
        default=10, verbose_name="Total de Sellos/Firmas Esperados"
    )

    class Meta:
        verbose_name = "Tarea / Cuaderno"
        verbose_name_plural = "Tareas y Cuadernos"

    def __str__(self):
        return f"[{self.get_tipo_tarea_display()}] {self.titulo}"


class EntregaTarea(models.Model):
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE)
    estudiante = models.ForeignKey(EstudiantePerfil, on_delete=models.CASCADE)
    archivo = models.FileField(upload_to="entregas/", blank=True, null=True)
    nota_calculada = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    estado_materia = models.CharField(max_length=100, blank=True, null=True)
    sellos_deberes = models.PositiveIntegerField(default=0)
    sellos_talleres = models.PositiveIntegerField(default=0)
    sellos_atrasados = models.PositiveIntegerField(default=0)
    observacion_ia = models.TextField(blank=True, null=True)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de Tarea"
        verbose_name_plural = "Registros de Tareas"

    def __str__(self):
        return f"{self.estudiante.nombre_completo} - {self.tarea.titulo}"


class Evaluacion(models.Model):
    titulo = models.CharField(max_length=200, verbose_name="Título del Módulo / Evaluación")
    descripcion = models.TextField(blank=True, null=True)
    enlace_externo = models.URLField(blank=True, null=True)
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Módulo de Clase y Lección"
        verbose_name_plural = "Módulos de Clase y Lecciones"

    def __str__(self):
        return f"{self.titulo} - {self.curso.nombre}"


class ResultadoEvaluacion(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE)
    estudiante = models.ForeignKey(EstudiantePerfil, on_delete=models.CASCADE)
    nota_obtenida = models.DecimalField(max_digits=4, decimal_places=2)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Calificación de Lección"
        verbose_name_plural = "Calificaciones de Lecciones"

    def __str__(self):
        return f"{self.estudiante.nombre_completo}: {self.nota_obtenida}"


class ModuloInteractivo(models.Model):
    ESPECIALIDADES = [
        ("Contabilidad", "Contabilidad"),
        ("Informática", "Informática"),
        ("Ventas", "Ventas"),
        ("Agropecuaria", "Agropecuaria"),
        ("Tronco Común / BGU", "Tronco Común / BGU"),
    ]
    PARALELOS = [
        ("A", "Paralelo A"),
        ("B", "Paralelo B"),
        ("C", "Paralelo C"),
    ]

    titulo = models.CharField(max_length=200, verbose_name="Tema del Módulo")
    asignatura = models.CharField(
        max_length=120, default="Matemática", verbose_name="Asignatura"
    )
    institucion = models.CharField(
        max_length=200,
        default='UNIDAD EDUCATIVA TÉCNICA "DR. ENRIQUE NOBOA" • LA TRONCAL',
        verbose_name="Encabezado Institucional",
    )
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso")
    especialidad = models.CharField(
        max_length=60,
        choices=ESPECIALIDADES,
        default="Informática",
        verbose_name="Figura Profesional",
    )
    paralelo = models.CharField(
        max_length=5, choices=PARALELOS, default="A", verbose_name="Paralelo"
    )
    destreza_indicadores = models.TextField(
        blank=True, null=True, verbose_name="Destreza e Indicadores de Evaluación"
    )
    tiempo_minutos = models.PositiveIntegerField(
        default=30, verbose_name="Tiempo de Evaluación (min)"
    )
    contenido_json = models.TextField(verbose_name="Contenido Estructurado (JSON IA)")
    evaluacion_vinculada = models.ForeignKey(
        Evaluacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Evaluación Vinculada en Notas",
    )
    tarea_deber_vinculada = models.ForeignKey(
        Tarea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Tarea/Deber Vinculado",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Módulo Interactivo IA"
        verbose_name_plural = "Módulos Interactivos IA"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.titulo} ({self.curso})"


class EsquelaIncumplimiento(models.Model):
    estudiante = models.ForeignKey(
        EstudiantePerfil, on_delete=models.CASCADE, verbose_name="Estudiante"
    )
    fecha_emision = models.DateTimeField(auto_now_add=True)
    motivo_principal = models.CharField(
        max_length=200,
        default="Incumplimiento de Deberes, Talleres y Evaluaciones",
        verbose_name="Motivo",
    )
    detalle_incumplimiento = models.TextField(verbose_name="Detalle de Actividades Pendientes")
    plazo_entrega = models.CharField(
        max_length=100, default="48 horas hábiles", verbose_name="Plazo de Regularización"
    )
    enviada_whatsapp = models.BooleanField(default=False, verbose_name="Notificada por WhatsApp")
    observacion_docente = models.TextField(
        blank=True, null=True, verbose_name="Observación Adicional"
    )

    class Meta:
        verbose_name = "Esquela de Incumplimiento"
        verbose_name_plural = "Esquelas de Incumplimiento"
        ordering = ["-fecha_emision"]

    def __str__(self):
        return f"Esquela - {self.estudiante.nombre_completo} ({self.fecha_emision.strftime('%d/%m/%Y')})"


class RegistroAsistencia(models.Model):
    ESTADOS = [
        ("P", "Presente"),
        ("F", "Falta"),
        ("A", "Atraso"),
        ("J", "Justificado"),
        ("FG", "Fuga"),
    ]
    estudiante = models.ForeignKey(
        EstudiantePerfil, on_delete=models.CASCADE, related_name="asistencias"
    )
    fecha = models.DateField(verbose_name="Fecha de Sesión")
    estado = models.CharField(max_length=2, choices=ESTADOS, default="P")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("estudiante", "fecha")
        verbose_name = "Registro de Asistencia"
        verbose_name_plural = "Registros de Asistencia"

    def __str__(self):
        return f"{self.estudiante.nombre_completo} - {self.fecha}: {self.estado}"


class RegistroPizarra(models.Model):
    CALIFICACIONES_CUALI = [
        ("10", "10 - Sobresaliente"),
        ("9", "9 - Muy Buena"),
        ("8", "8 - Buena"),
        ("7", "7 - Alcanza"),
        ("6", "6 - Regular"),
        ("5", "5 - Insuficiente"),
        ("2", "2 - Mínima"),
        ("EP", "Excelente Participación"),
        ("BP", "Buena Participación"),
        ("DP", "Débil Participación"),
        ("NP", "No Pasó / No Participó"),
    ]
    estudiante = models.ForeignKey(
        EstudiantePerfil, on_delete=models.CASCADE, related_name="pizarras"
    )
    fecha = models.DateField(verbose_name="Fecha de Sesión")
    codigo_cuali = models.CharField(max_length=10, choices=CALIFICACIONES_CUALI)
    nota_cuanti = models.DecimalField(max_digits=4, decimal_places=2)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("estudiante", "fecha")
        verbose_name = "Lección / Pizarra"
        verbose_name_plural = "Lecciones / Pizarra"

    def __str__(self):
        return f"{self.estudiante.nombre_completo} - {self.fecha}: {self.codigo_cuali} ({self.nota_cuanti})"