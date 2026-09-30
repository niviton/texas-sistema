import io
import re

from django import forms
from django.core.files.base import ContentFile
from PIL import Image

from .imagetools import remove_background
from .models import CERT_TYPE_CHOICES, CertificateSettings, CourseTemplate, Professor


class _SubjectCpfValidationMixin:
    def clean_subject_code(self):
        code = self.cleaned_data['subject_code'].strip()
        if not code.isdigit() or len(code) != 9:
            raise forms.ValidationError('Informe os 9 dígitos do assunto.')
        return code

    def clean_cpf(self):
        cpf = re.sub(r'\D', '', self.cleaned_data['cpf'])
        if len(cpf) != 11:
            raise forms.ValidationError('CPF inválido.')
        return cpf


class ManualIssueForm(_SubjectCpfValidationMixin, forms.Form):
    course_template = forms.ModelChoiceField(queryset=CourseTemplate.objects.all(), label='Certificado (modelo)')
    cert_type = forms.ChoiceField(choices=CERT_TYPE_CHOICES, initial='interno', label='Tipo de certificado')
    professor = forms.ModelChoiceField(queryset=Professor.objects.filter(is_active=True), label='Instrutor responsável')
    subject_code = forms.CharField(max_length=9, label='Assunto (código do cliente/empresa)')
    client_name = forms.CharField(max_length=150, label='Cliente / local do curso')
    student_name = forms.CharField(max_length=150, label='Nome do aluno')
    cpf = forms.CharField(max_length=14, label='CPF do aluno')
    course_date = forms.DateField(label='Data', widget=forms.DateInput(attrs={'type': 'date'}))
    duration = forms.IntegerField(min_value=1, label='Duração (horas)', widget=forms.NumberInput())
    issue_date = forms.DateField(label='Data de emissão', widget=forms.DateInput(attrs={'type': 'date'}))


class StudentRegistrationForm(_SubjectCpfValidationMixin, forms.Form):
    professor = forms.ModelChoiceField(queryset=Professor.objects.filter(is_active=True), label='Instrutor responsável')
    cert_type = forms.ChoiceField(choices=CERT_TYPE_CHOICES, initial='interno', label='Tipo de certificado')
    subject_code = forms.CharField(max_length=9, label='Assunto (código do cliente/empresa)')
    client_name = forms.CharField(max_length=150, label='Cliente / local do curso')
    course_date = forms.DateField(label='Data do curso', widget=forms.DateInput(attrs={'type': 'date'}))
    duration = forms.IntegerField(min_value=1, label='Duração (horas)', widget=forms.NumberInput())
    student_name = forms.CharField(max_length=150, label='Nome do aluno')
    cpf = forms.CharField(max_length=14, label='CPF do aluno')


class ProfessorForm(forms.ModelForm):
    class Meta:
        model = Professor
        fields = [
            'full_name', 'sigla', 'signature', 'is_chief', 'chief_cert_type',
            'signature_offset_x_pt', 'signature_offset_y_pt',
            'signature_light_threshold', 'signature_dark_threshold', 'signature_invert_colors',
        ]
        widgets = {
            'chief_cert_type': forms.Select(choices=[('', '—')] + CERT_TYPE_CHOICES),
        }

    def clean_sigla(self):
        sigla = self.cleaned_data['sigla'].upper().strip()
        qs = Professor.objects.filter(sigla=sigla)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Já existe um professor com essa sigla.')
        return sigla

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('is_chief'):
            chief_type = cleaned_data.get('chief_cert_type')
            if not chief_type:
                self.add_error('chief_cert_type', 'Selecione o tipo de certificado para o instrutor chefe.')
            else:
                qs = Professor.objects.filter(is_chief=True, chief_cert_type=chief_type)
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                existing = qs.first()
                if existing:
                    self.add_error(
                        'chief_cert_type',
                        f'{existing.full_name} já é o instrutor chefe para certificados '
                        f'{dict(CERT_TYPE_CHOICES).get(chief_type, chief_type)}. Remova essa marcação dele antes.',
                    )
        light = cleaned_data.get('signature_light_threshold')
        dark = cleaned_data.get('signature_dark_threshold')
        if light is not None and dark is not None and light <= dark:
            self.add_error('signature_light_threshold', 'O limite de branco deve ser maior que o limite de preto.')
        return cleaned_data

    _TONE_FIELDS = {'signature_light_threshold', 'signature_dark_threshold', 'signature_invert_colors'}

    def save(self, commit=True):
        professor = super().save(commit=False)
        should_reprocess = professor.signature and (
            'signature' in self.changed_data or self._TONE_FIELDS & set(self.changed_data)
        )
        if should_reprocess:
            image = Image.open(professor.signature)
            processed = remove_background(
                image,
                light_threshold=professor.signature_light_threshold,
                dark_threshold=professor.signature_dark_threshold,
                invert=professor.signature_invert_colors,
            )
            buffer = io.BytesIO()
            processed.save(buffer, format='PNG')
            filename = f'{professor.sigla or "professor"}_signature.png'
            professor.signature.save(filename, ContentFile(buffer.getvalue()), save=False)
        if commit:
            professor.save()
        return professor


class CourseTemplateForm(forms.ModelForm):
    class Meta:
        model = CourseTemplate
        fields = ['title', 'default_subject_number', 'syllabus_items', 'default_duration', 'word_template']
        widgets = {
            'syllabus_items': forms.Textarea(attrs={'rows': 6}),
        }

    def clean_default_subject_number(self):
        value = self.cleaned_data.get('default_subject_number', '').strip()
        if value and (not value.isdigit() or len(value) != 9):
            raise forms.ValidationError('Informe os 9 dígitos do assunto ou deixe em branco.')
        return value


class CertificateSettingsForm(forms.ModelForm):
    class Meta:
        model = CertificateSettings
        fields = ['show_qr_code', 'signature_width_pt', 'signature_height_pt']
