from django.db import models


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
        ('materia', 'Materia'),
        ('deber', 'Deber'),
        ('taller', 'Taller'),
    ]

    titulo = models.CharField(max_length=200, verbose_name="Título de la Tarea / Cuaderno")
    descripcion = models.TextField(verbose_name="Instrucciones o Contenido")
    curso = models.ForeignKey(CursoBGU, on_delete=models.CASCADE, verbose_name="Curso BGU")
    fecha_limite = models.DateTimeField(verbose_name="Fecha Límite")
    tipo_tarea = models.CharField(max_length=50, choices=TIPO_CHOICES, default='deber', verbose_name="Tipo")

    class Meta:
        verbose_name = "Tarea / Cuaderno"
        verbose_name_plural = "Tareas y Cuadernos"

    def __str__(self):
        return f"[{self.get_tipo_tarea_display()}] {self.titulo}"


class EntregaTarea(models.Model):
    ESTADO_MATERIA_CHOICES = [
        ('completo', 'Completo'),
        ('incompleto', 'Incompleto'),
    ]

    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, verbose_name="Tarea / Cuaderno")
    estudiante = models.ForeignKey(EstudiantePerfil, on_delete=models.CASCADE, verbose_name="Estudiante")
    archivo_estudiante = models.FileField(upload_to='tareas/', blank=True, null=True, verbose_name="Archivo")

    estado_materia = models.CharField(
        max_length=20,
        choices=ESTADO_MATERIA_CHOICES,
        blank=True,
        null=True,
        verbose_name="Estado de Materia"
    )
    sellos_deberes = models.IntegerField(default=0, verbose_name="Número de Sellos de Deberes")
    sellos_talleres = models.IntegerField(default=0, verbose_name="Número de Sellos de Talleres")

    nota_calculada = models.FloatField(default=5.0, verbose_name="Nota Calculada")
    fecha_envio = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    class Meta:
        verbose_name = "Registro de Tarea"
        verbose_name_plural = "Registros de Tareas"

    def __str__(self):
        return f"Entrega de {self.estudiante} para {self.tarea}"


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