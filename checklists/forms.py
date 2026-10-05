from django import forms

from .models import Ativo, Item, Modelo, Revisao, Secao, TipoAtivo

_DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class TipoAtivoForm(forms.ModelForm):
    class Meta:
        model = TipoAtivo
        fields = ['nome', 'medidor', 'descricao']


class AtivoForm(forms.ModelForm):
    class Meta:
        model = Ativo
        fields = ['tipo', 'nome', 'identificacao', 'patrimonio', 'marca', 'modelo', 'status', 'medidor_atual', 'observacoes']
        widgets = {'observacoes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].queryset = TipoAtivo.objects.filter(is_active=True)


class ModeloForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ['codigo', 'titulo', 'tipos_ativo', 'is_active']
        widgets = {'tipos_ativo': forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipos_ativo'].queryset = TipoAtivo.objects.filter(is_active=True)
        self.fields['tipos_ativo'].help_text = 'Os técnicos só veem este checklist nos equipamentos desses tipos.'

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()


class RevisaoForm(forms.ModelForm):
    class Meta:
        model = Revisao
        fields = ['preparado_por', 'revisado_por', 'data', 'notas']
        widgets = {'data': _DATE}


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ['titulo']


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['texto', 'tipo_resposta', 'exige_foto', 'observacao']


class ImportarForm(forms.Form):
    arquivo = forms.FileField(label='Formulário em Word (.docx)')
    tipo_ativo = forms.ModelChoiceField(
        queryset=TipoAtivo.objects.filter(is_active=True), required=False, label='Aplica-se ao tipo de ativo',
        empty_label='Criar a partir do título do formulário',
    )

    def clean_arquivo(self):
        f = self.cleaned_data['arquivo']
        if not f.name.lower().endswith('.docx'):
            raise forms.ValidationError('Envie o formulário em Word (.docx). Arquivos .doc antigos precisam ser salvos como .docx.')
        return f


class NovoModeloForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ['codigo', 'titulo', 'tipos_ativo']
        widgets = {'tipos_ativo': forms.CheckboxSelectMultiple}

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()
