from django import forms

from .models import (
    CATEGORIA_CAMINHONETE, TIPO_CHEGADA, TIPO_CHOICES, TIPO_SAIDA, Manutencao, Motorista, Supervisor, Veiculo,
    motorista_do_usuario,
)

_DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class SupervisorForm(forms.ModelForm):
    class Meta:
        model = Supervisor
        fields = ['name', 'email']


class MotoristaForm(forms.ModelForm):
    class Meta:
        model = Motorista
        fields = ['name', 'usuario', 'email', 'phone', 'cnh_numero', 'cnh_validade']
        widgets = {'cnh_validade': _DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import User
        self.fields['usuario'].queryset = User.objects.filter(role__in=[User.ROLE_TECNICO, User.ROLE_LOGISTICA]).order_by('full_name')


class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = [
            'placa', 'categoria', 'marca', 'modelo', 'ano', 'cor', 'km_atual', 'foto', 'motorista_responsavel',
            'licenciamento_validade', 'seguro_validade', 'revisao_data', 'revisao_km',
            'checklist_frequencia_dias',
        ]
        widgets = {
            'licenciamento_validade': _DATE,
            'seguro_validade': _DATE,
            'revisao_data': _DATE,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motorista_responsavel'].queryset = Motorista.objects.filter(is_active=True)


class ManutencaoForm(forms.ModelForm):
    class Meta:
        model = Manutencao
        fields = ['nome', 'proximo_km', 'proxima_data', 'intervalo_km', 'intervalo_meses', 'aviso_km', 'aviso_dias']
        widgets = {'proxima_data': _DATE}

    def clean(self):
        data = super().clean()
        if not data.get('proximo_km') and not data.get('proxima_data'):
            raise forms.ValidationError('Informe o km e/ou a data da próxima manutenção.')
        return data


class InspecaoForm(forms.Form):
    """Cabeçalho da inspeção. Os itens do checklist e as fotos são lidos direto do POST na view."""
    veiculo = forms.ModelChoiceField(queryset=Veiculo.objects.filter(is_active=True), label='Veículo')
    motorista = forms.ModelChoiceField(queryset=Motorista.objects.filter(is_active=True), label='Motorista')
    tipo = forms.ChoiceField(choices=TIPO_CHOICES, label='Tipo')
    km = forms.IntegerField(min_value=0, label='Km no painel')
    combustivel_pct = forms.IntegerField(
        min_value=0, max_value=100, label='Combustível', widget=forms.HiddenInput,
        error_messages={'required': 'Informe o nível de combustível.'},
    )
    com_carga = forms.ChoiceField(
        choices=[('sim', 'Sim'), ('nao', 'Não')], label='Leva carga?', required=False, widget=forms.RadioSelect,
    )
    observacoes = forms.CharField(label='Observações gerais', required=False, widget=forms.Textarea)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Quem faz a vistoria (Técnico ou Logística) é o próprio motorista: não escolhe ninguém.
        if user is not None and not user.is_admin_geral:
            del self.fields['motorista']

    def clean(self):
        data = super().clean()
        if 'motorista' not in self.fields and self.user is not None:
            data['motorista'] = motorista_do_usuario(self.user)
        veiculo, tipo, km = data.get('veiculo'), data.get('tipo'), data.get('km')
        if veiculo and veiculo.categoria == CATEGORIA_CAMINHONETE and not data.get('com_carga'):
            self.add_error('com_carga', 'Informe se a caminhonete leva carga.')
        if not veiculo or km is None:
            return data
        uso = veiculo.uso_aberto
        if tipo == TIPO_SAIDA and uso:
            raise forms.ValidationError(
                f'{veiculo.placa} já está em uso (saída em {uso.saida_em:%d/%m/%Y %H:%M}). Registre a chegada primeiro.'
            )
        if tipo == TIPO_CHEGADA:
            if not uso:
                raise forms.ValidationError(f'{veiculo.placa} não tem saída em aberto para registrar a chegada.')
            if self.user is not None and not self.user.is_admin_geral and uso.motorista_id != data['motorista'].pk:
                raise forms.ValidationError(f'{veiculo.placa} está em uso por outro condutor. Só quem registrou a saída pode registrar a chegada.')
            if km < uso.km_saida:
                self.add_error('km', f'O km de chegada não pode ser menor que o de saída ({uso.km_saida}).')
        elif km < veiculo.km_atual:
            self.add_error('km', f'O km informado é menor que o último registrado ({veiculo.km_atual}).')
        return data
