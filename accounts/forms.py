import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Papel, User


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='E-mail')

    error_messages = {
        **AuthenticationForm.error_messages,
        'inactive': 'Sua conta ainda não foi aprovada por um administrador.',
    }

    def confirm_login_allowed(self, user):
        if not user.is_approved:
            raise forms.ValidationError(
                self.error_messages['inactive'],
                code='inactive',
            )


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label='Senha', min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirmar senha')
    terms = forms.BooleanField(label='Aceito os termos de uso', error_messages={
        'required': 'É necessário aceitar os termos de uso.',
    })

    class Meta:
        model = User
        fields = ['full_name', 'cpf', 'phone', 'email']

    def clean_cpf(self):
        cpf = re.sub(r'\D', '', self.cleaned_data.get('cpf', ''))
        if len(cpf) != 11:
            raise forms.ValidationError('Informe um CPF válido.')
        return cpf

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password2 = cleaned_data.get('password2')
        if password and password2 and password != password2:
            self.add_error('password2', 'As senhas não coincidem.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = User.ROLE_PENDENTE  # sem acesso até o administrador dar um papel
        user.is_approved = False
        if commit:
            user.save()
        return user


class PapelForm(forms.ModelForm):
    class Meta:
        model = Papel
        fields = ['nome', 'descricao', 'acesso_vistoria', 'acesso_checklists', 'acesso_termos', 'acesso_certificados',
                  've_todo_historico', 'administrador']
        widgets = {'descricao': forms.TextInput(attrs={'placeholder': 'Ex.: Motoristas da frota, só fazem vistoria.'})}

    def clean(self):
        dados = super().clean()
        campos = ['administrador', 'acesso_vistoria', 'acesso_checklists', 'acesso_termos', 'acesso_certificados']
        if not any(dados.get(c) for c in campos):
            raise forms.ValidationError('Marque pelo menos um acesso para este papel.')
        return dados


class AdminUserEditForm(forms.ModelForm):
    new_password = forms.CharField(
        label='Nova senha', widget=forms.PasswordInput, required=False, min_length=8,
        help_text='Deixe em branco para manter a senha atual.',
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'cpf', 'phone', 'papel', 'is_approved']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = Papel.objects.filter(is_active=True)
        self.fields['papel'].required = True
        self.fields['papel'].empty_label = 'Escolha o papel'

    def clean_cpf(self):
        cpf = re.sub(r'\D', '', self.cleaned_data.get('cpf', ''))
        if cpf and len(cpf) != 11:
            raise forms.ValidationError('Informe um CPF válido.')
        return cpf

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get('new_password')
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user
