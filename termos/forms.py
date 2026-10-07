from django import forms

from .models import ModeloTermo, Termo

_DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class TermoForm(forms.ModelForm):
    class Meta:
        model = Termo
        fields = ['tipo', 'numero_assunto', 'motivo', 'data', 'cliente_contato', 'origem', 'transporte',
                  'observacoes', 'nome_cliente', 'telefone_cliente']
        widgets = {
            'data': _DATE,
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'tipo': forms.RadioSelect,
        }
        error_messages = {
            'data': {'required': 'Informe a data.'},
            'cliente_contato': {'required': 'Informe o cliente e a pessoa de contato.'},
        }


class ModeloTermoForm(forms.ModelForm):
    class Meta:
        model = ModeloTermo
        fields = ['codigo', 'titulo', 'revisao', 'preparado_por', 'revisado_por', 'data']
        widgets = {'data': _DATE}


class ImportarTermoForm(forms.Form):
    arquivo = forms.FileField(label='Formulário em Word (.docx)')

    def clean_arquivo(self):
        f = self.cleaned_data['arquivo']
        if not f.name.lower().endswith('.docx'):
            raise forms.ValidationError('Envie o formulário em Word (.docx).')
        return f
