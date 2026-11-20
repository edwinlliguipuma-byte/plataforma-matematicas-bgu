from django import forms
from .models import EntregaTarea

class EntregaTareaForm(forms.ModelForm):
    cedula = forms.CharField(max_length=20, label="Número de Cédula (Contraseña)")

    class Meta:
        model = EntregaTarea
        fields = ['cedula', 'archivo_estudiante', 'firmas_reportadas', 'estado_materia']
        widgets = {
            'archivo_estudiante': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'firmas_reportadas': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 5'}),
            'estado_materia': forms.Select(attrs={'class': 'form-control'}),
        }