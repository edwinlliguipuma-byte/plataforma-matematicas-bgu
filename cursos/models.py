import base64
from django.db import models


def _mime_desde_nombre(nombre_archivo):
    nombre = (nombre_archivo or '').lower()
    if nombre.endswith('.png'):
        return 'image/png'
    if nombre.endswith('.webp'):
        return 'image/webp'
    return 'image/jpeg'


class MuestraSelloFirma(models.Model):
    nombre = models.CharField(
        max_length=150,
        default="Sello y Firma Oficial del Docente",
        verbose_name="Nombre Identificador"
    )
    imagen_sello = models.ImageField(
        upload_to='sellos_referencia/',
        blank=True,
        null=True,
        verbose_name="Foto del Sello Oficial"
    )
    imagen_firma = models.ImageField(
        upload_to='sellos_referencia/',
        blank=True,
        null=True,
        verbose_name="Foto de la Firma a Mano (y ejemplo de marca 'A' si deseas)"
    )
    descripcion_visual = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descripción del Sello, Firma y Marca 'A'",
        help_text="Ej: Sello azul de la U.E. Dr. Enrique Noboa - Matemática y rúbrica con esfero azul. Cuando es atrasado escribo una letra 'A' junto al sello."
    )
    sello_base64 = models.TextField(blank=True, null=True, editable=False)
    sello_mime = models.CharField(max_length=50, blank=True, null=True, editable=False)
    firma_base64 = models.TextField(blank=True, null=True, editable=False)
    firma_mime = models.CharField(max_length=50, blank=True, null=True, editable=False)
    activo = models.BooleanField(default=True, verbose_name="Activo para Calificación IA")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Última Actualización")

    class Meta:
        verbose_name = "Muestra de Sello y Firma"
        verbose_name_plural = "Muestras de Sello y Firma"
        ordering = ['-fecha_actualizacion']

    def save(self, *args, **kwargs):
        if self.imagen_sello and hasattr(self.imagen_sello, 'file'):
            try:
                self.imagen_sello.seek(0)
                raw_sello = self.imagen_sello.read()
                if raw_sello:
                    self.sello_base64 = base64.b64encode(raw_sello).decode('utf-8')
                    self.sello_mime = _mime_desde_nombre(self.imagen_sello.name)
                self.imagen_sello.seek(0)
            except Exception:
                pass

        if self.imagen_firma and hasattr(self.imagen_firma, 'file'):
            try:
                self.imagen_firma.seek(0)
                raw_firma = self.imagen_firma.read()
                if raw_firma:
                    self.firma_base64 = base64.b64encode(raw_firma).decode('utf-8')
                    self.firma_mime = _mime_desde_nombre(self.imagen_firma.name)
                self.imagen_firma.seek(0)
            except Exception:
                pass

        super().save(*args, **kwargs)

    def __str__(self):
        estado = "Activo" if self.activo else "Inactivo"
        return f"{self.nombre} ({estado})"


class CursoBGU(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Curso")

    class Meta:
        verbose_name = "Curso BGU"
        verbose_name_plural = "Cursos BGU"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class EstudiantePerfil(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    apellidos_nombres = models.CharField(max_length=200, blank=True, null=True, verbose_name="Apellidos y Nombres")
    cedula = models.CharField(max_length=20, unique=True, verbose_name="Cédula")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")

    class Meta:
        verbose_name = "Estudiante"
        verbose_name_plural = "Estudiantes"
        ordering = ['apellidos_nombres', 'cedula']

    @property
    def nombre_completo(self):
        if self.apellidos_nombres and self.apellidos_nombres.strip():
            return self.apellidos_nombres.strip()
        if self.user:
            nombre_usuario = f"{self.user.last_name} {self.user.first_name}".strip()
            if nombre_usuario:
                return nombre_usuario
            if self.user.username:
                return self.user.username
        return self.cedula

    def __str__(self):
        return f"{self.nombre_completo} - {self.curso}"


class Tarea(models.Model):
    TIPO_CHOICES = [
        ('materia', 'Materia (Carátula, Presentación y Completitud: 6 a 10 pts)'),
        ('deber', 'Deber (Conteo de Sellos/Firmas + Atrasados "A")'),
        ('taller', 'Taller (Conteo de Sellos/Firmas + Atrasados "A")'),
    ]

    titulo = models.CharField(max_length=200, verbose_name="Título de la Tarea / Cuaderno")
    descripcion = models.TextField(verbose_name="Instrucciones o Temas a Revisar")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    fecha_limite = models.DateTimeField(verbose_name="Fecha Límite")
    tipo_tarea = models.CharField(max_length=50, choices=TIPO_CHOICES, default='deber', verbose_name="Tipo")
    total_sellos_esperados = models.PositiveIntegerField(
        default=10,
        verbose_name="Total de Sellos/Firmas Esperados",
        help_text="Solo para Deberes o Talleres: indica cuántos sellos o firmas completos equivalen a 10 puntos."
    )

    class Meta:
        verbose_name = "Tarea / Cuaderno"
        verbose_name_plural = "Tareas y Cuadernos"
        ordering = ['-fecha_limite']

    def __str__(self):
        return f"[{self.get_tipo_tarea_display()}] {self.titulo} ({self.curso})"


class EntregaTarea(models.Model):
    ESTADO_MATERIA_CHOICES = [
        ('completo', 'Completo'),
        ('incompleto', 'Incompleto'),
    ]

    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, verbose_name="Tarea / Cuaderno")
    estudiante = models.ForeignKey(EstudiantePerfil, on_delete=models.CASCADE, verbose_name="Estudiante")
    archivo_estudiante = models.FileField(upload_to='tareas/', blank=True, null=True, verbose_name="Archivo Subido")

    estado_materia = models.CharField(
        max_length=20,
        choices=ESTADO_MATERIA_CHOICES,
        blank=True,
        null=True,
        verbose_name="Estado de Materia"
    )
    sellos_deberes = models.IntegerField(default=0, verbose_name="Sellos/Firmas Completos (1 pt)")
    sellos_talleres = models.IntegerField(default=0, verbose_name="Sellos/Firmas Talleres (1 pt)")
    sellos_atrasados = models.IntegerField(default=0, verbose_name="Sellos Atrasados 'A' (0.5 pts)")

    nota_calculada = models.FloatField(default=6.0, verbose_name="Nota Calculada (/10)")
    observacion_ia = models.TextField(blank=True, null=True, verbose_name="Detalle de Calificación IA")
    fecha_envio = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    class Meta:
        verbose_name = "Registro de Tarea"
        verbose_name_plural = "Registros de Tareas"
        ordering = ['-fecha_envio']

    def __str__(self):
        return f"Entrega de {self.estudiante} para {self.tarea} ({self.nota_calculada}/10)"


class Evaluacion(models.Model):
    titulo = models.CharField(max_length=200, verbose_name="Título del Módulo / Lección")
    descripcion = models.TextField(verbose_name="Instrucciones y Enlace del Simulador")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Módulo de Clase y Lección"
        verbose_name_plural = "Módulos de Clase y Lección"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.titulo} - {self.curso}"


class ResultadoEvaluacion(models.Model):
    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, verbose_name="Módulo / Lección")
    estudiante = models.ForeignKey(EstudiantePerfil, on_delete=models.CASCADE, verbose_name="Estudiante")
    nota_obtenida = models.FloatField(verbose_name="Nota Obtenida")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    class Meta:
        verbose_name = "Calificación de Lección"
        verbose_name_plural = "Calificaciones de Lecciones"
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.estudiante} - {self.evaluacion}: {self.nota_obtenida}"