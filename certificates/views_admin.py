import base64
import re
import zipfile
from datetime import date
from io import BytesIO

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import admin_required
from .forms import CertificateSettingsForm, CourseTemplateForm, ManualIssueForm, ProfessorForm
from .imports import parse_spreadsheet
from .models import Certificate, CertificateSettings, CourseTemplate, Professor, STATUS_APPROVED, STATUS_PENDING, STATUS_REJECTED, StudentRegistration
from .pdf import render_certificate, render_certificate_png
from .sharepoint_sim import write_certificate_to_simulation

CERT_TABS = [
    ('pendentes', 'Pendentes', 'cert_admin:pendentes'),
    ('emitir', 'Emitir manualmente', 'cert_admin:emitir'),
    ('historico', 'Histórico', 'cert_admin:historico'),
    ('professores', 'Professores', 'cert_admin:professores'),
    ('importar', 'Importar planilha', 'cert_admin:importar'),
    ('modelos', 'Modelos de certificado', 'cert_admin:modelos'),
    ('configuracoes', 'Configurações', 'cert_admin:configuracoes'),
]


def _cert_context(active_tab, **extra):
    context = {'active_nav': 'certificados', 'cert_tabs': CERT_TABS, 'active_tab': active_tab}
    context.update(extra)
    return context


def _build_certificate_from_form(data, code):
    return Certificate(
        code=code,
        student_name=data['student_name'],
        cpf=data['cpf'],
        course_template=data['course_template'],
        course_title=data['course_template'].title,
        client_name=data['client_name'],
        professor=data['professor'],
        subject_code=data['subject_code'],
        cert_type=data['cert_type'],
        course_date=data['course_date'],
        duration=f"{data['duration']} HORAS",
        issue_date=data['issue_date'],
    )


_LAST_MANUAL_ISSUE_SESSION_KEY = 'last_manual_issue'


def _remembered_manual_issue_initial(request):
    """Pre-fills everything except student_name/cpf/issue_date from the admin's last
    emitted certificate, so a batch of students for the same session only needs those
    fields retyped each time. issue_date always defaults to today instead, since it's
    tied to when the certificate is actually being issued, not to the previous one."""
    initial = dict(request.session.get(_LAST_MANUAL_ISSUE_SESSION_KEY, {}))
    initial['issue_date'] = date.today().isoformat()
    return initial


def _remember_manual_issue(request, data):
    request.session[_LAST_MANUAL_ISSUE_SESSION_KEY] = {
        'course_template': data['course_template'].pk,
        'cert_type': data['cert_type'],
        'professor': data['professor'].pk,
        'subject_code': data['subject_code'],
        'client_name': data['client_name'],
        'course_date': data['course_date'].isoformat(),
        'duration': data['duration'],
    }


@admin_required
def emitir_view(request):
    certificate = None
    preview_data_uri = None

    if request.method == 'POST':
        action = request.POST.get('action', 'issue')
        form = ManualIssueForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            code = Certificate.build_code(data['subject_code'], data['professor'].sigla)

            if action == 'preview':
                # Unsaved instance — nothing is written to the database for a preview.
                preview_cert = _build_certificate_from_form(data, code)
                try:
                    png_bytes = render_certificate_png(
                        preview_cert, verify_url=_verify_url(request, preview_cert.code),
                    ).getvalue()
                    preview_data_uri = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')
                except Exception as exc:
                    messages.error(request, f'Não foi possível gerar a pré-visualização: {exc}')
            else:
                certificate = _build_certificate_from_form(data, code)
                certificate.created_by = request.user
                try:
                    certificate.save()
                except Exception as exc:
                    certificate = None
                    messages.error(request, f'Não foi possível emitir o certificado: {exc}')
                else:
                    try:
                        write_certificate_to_simulation(certificate, request=request)
                    except Exception:
                        pass
                    _remember_manual_issue(request, data)
                    form = ManualIssueForm(initial=_remembered_manual_issue_initial(request))
    else:
        form = ManualIssueForm(initial=_remembered_manual_issue_initial(request))

    subject_codes = []
    seen_codes = set()
    for code in Certificate.objects.exclude(subject_code='').order_by('-pk').values_list('subject_code', flat=True):
        if code not in seen_codes:
            seen_codes.add(code)
            subject_codes.append(code)
            if len(subject_codes) >= 200:
                break

    client_names = []
    seen_names = set()
    for name in Certificate.objects.exclude(client_name='').order_by('-pk').values_list('client_name', flat=True):
        if name not in seen_names:
            seen_names.add(name)
            client_names.append(name)
            if len(client_names) >= 200:
                break

    return render(request, 'certificates/emitir.html', _cert_context(
        'emitir', form=form, certificate=certificate, preview_data_uri=preview_data_uri,
        has_professors=Professor.objects.exists(), has_templates=CourseTemplate.objects.exists(),
        subject_codes=subject_codes, client_names=client_names,
    ))


def _verify_url(request, code):
    return request.build_absolute_uri(reverse('certificates:verify')) + f'?code={code}'


@admin_required
def cpf_lookup_ajax_view(request):
    """Looks up the most recent student name on record for a given CPF, so the emit
    form can auto-fill the name field as the admin types a CPF that's been seen before."""
    cpf_digits = re.sub(r'\D', '', request.GET.get('cpf', ''))
    if len(cpf_digits) != 11:
        return HttpResponse(status=422)
    cert = Certificate.objects.filter(cpf=cpf_digits).order_by('-issue_date', '-pk').first()
    if not cert:
        return HttpResponse(status=404)
    return JsonResponse({'student_name': cert.student_name})


@admin_required
def emitir_preview_ajax_view(request):
    """Same preview render as emitir_view's 'preview' action, but returns just the raw PNG
    (or a non-200 with no body) for the live-updating preview panel to fetch() on field
    change. Silently 422s when the form isn't complete enough to render yet — the caller
    is expected to just leave the previous preview showing rather than surface an error."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    form = ManualIssueForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=422)
    data = form.cleaned_data
    code = Certificate.build_code(data['subject_code'], data['professor'].sigla)
    preview_cert = _build_certificate_from_form(data, code)
    try:
        png_bytes = render_certificate_png(preview_cert, verify_url=_verify_url(request, preview_cert.code)).getvalue()
    except Exception:
        return HttpResponse(status=500)
    return HttpResponse(png_bytes, content_type='image/png')


@admin_required
def certificate_pdf_view(request, pk):
    certificate = get_object_or_404(Certificate, pk=pk)
    buffer = render_certificate(certificate, verify_url=_verify_url(request, certificate.code))
    return FileResponse(buffer, filename=f'{certificate.code} - {certificate.student_name}.pdf')


@admin_required
def certificate_preview_view(request, pk):
    certificate = get_object_or_404(Certificate, pk=pk)
    buffer = render_certificate_png(certificate, verify_url=_verify_url(request, certificate.code))
    return FileResponse(buffer, content_type='image/png')


@admin_required
def professores_view(request):
    editing = None
    edit_id = request.GET.get('edit')
    if edit_id:
        editing = get_object_or_404(Professor, pk=edit_id)

    if request.method == 'POST':
        instance = None
        post_edit_id = request.POST.get('editing_id')
        if post_edit_id:
            instance = get_object_or_404(Professor, pk=post_edit_id)
        form = ProfessorForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Professor salvo com sucesso.')
            return redirect('cert_admin:professores')
    else:
        form = ProfessorForm(instance=editing)

    show_archived = request.GET.get('arquivados') == '1'
    professors = Professor.objects.all() if show_archived else Professor.objects.filter(is_active=True)
    return render(request, 'certificates/professores.html', _cert_context(
        'professores', form=form, professors=professors, editing=editing, show_archived=show_archived,
    ))


@admin_required
def professor_archive_view(request, pk):
    professor = get_object_or_404(Professor, pk=pk)
    if request.method == 'POST':
        professor.is_active = not professor.is_active
        professor.save(update_fields=['is_active'])
        if professor.is_active:
            messages.success(request, f'{professor.full_name} reativado.')
        else:
            messages.success(request, f'{professor.full_name} arquivado. Ele não aparecerá mais para seleção em novos certificados.')
    return redirect('cert_admin:professores')


@admin_required
def pendentes_view(request):
    if request.method == 'POST':
        reg = get_object_or_404(StudentRegistration, pk=request.POST.get('registration_id'), status=STATUS_PENDING)
        action = request.POST.get('action')
        if action == 'approve':
            code = Certificate.build_code(reg.subject_code, reg.professor.sigla)
            certificate = Certificate.objects.create(
                code=code,
                student_name=reg.student_name,
                cpf=reg.cpf,
                course_template=reg.course_template,
                course_title=reg.course_template.title,
                client_name=reg.client_name,
                professor=reg.professor,
                subject_code=reg.subject_code,
                cert_type=reg.cert_type,
                course_date=reg.course_date,
                duration=reg.duration,
                issue_date=date.today(),
                created_by=request.user,
                source_registration=reg,
            )
            reg.status = STATUS_APPROVED
            reg.save(update_fields=['status'])
            try:
                write_certificate_to_simulation(certificate, request=request)
            except Exception:
                pass
            messages.success(request, f'Certificado {certificate.code} emitido.')
        elif action == 'reject':
            reg.status = STATUS_REJECTED
            reg.save(update_fields=['status'])
            messages.success(request, 'Cadastro rejeitado.')
        return redirect('cert_admin:pendentes')

    pending = StudentRegistration.objects.filter(status=STATUS_PENDING).select_related(
        'course_template', 'professor', 'created_by',
    ).order_by('subject_code', 'course_date')

    groups = {}
    for reg in pending:
        key = (reg.subject_code, reg.course_date, reg.professor_id)
        if key not in groups:
            groups[key] = {
                'subject_code': reg.subject_code,
                'course_date': reg.course_date,
                'course_title': reg.course_template.title,
                'professor_name': reg.professor.full_name,
                'rows': [],
            }
        groups[key]['rows'].append(reg)

    return render(request, 'certificates/pendentes.html', _cert_context(
        'pendentes', groups=groups.values(),
    ))


def _zip_response(certificates, request, filename):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for cert in certificates:
            if not cert.course_template_id:
                continue
            pdf_buffer = render_certificate(cert, verify_url=_verify_url(request, cert.code))
            zf.writestr(f'{cert.code} - {cert.student_name}.pdf', pdf_buffer.getvalue())
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@admin_required
def historico_view(request):
    query = request.GET.get('q', '').strip()
    certificates = Certificate.objects.select_related('professor', 'course_template').order_by(
        'subject_code', '-issue_date',
    )
    if query:
        cpf_digits = re.sub(r'\D', '', query)
        filters = (
            Q(student_name__icontains=query)
            | Q(code__icontains=query)
            | Q(subject_code__icontains=query)
        )
        if cpf_digits:
            filters |= Q(cpf__icontains=cpf_digits)
        certificates = certificates.filter(filters)

    groups = {}
    for cert in certificates:
        key = (cert.subject_code, cert.course_date, cert.professor_id)
        if key not in groups:
            groups[key] = {
                'subject_code': cert.subject_code,
                'course_date': cert.course_date,
                'course_title': cert.course_title,
                'professor_name': cert.instructor_name,
                'rows': [],
            }
        groups[key]['rows'].append(cert)

    return render(request, 'certificates/historico.html', _cert_context(
        'historico', groups=groups.values(), query=query,
    ))


@admin_required
def certificate_delete_view(request, pk):
    certificate = Certificate.objects.filter(pk=pk).first()
    if request.method == 'POST':
        if certificate:
            code = certificate.code
            certificate.delete()
            messages.success(request, f'Certificado {code} apagado.')
        else:
            messages.info(request, 'Esse certificado já havia sido apagado.')
    return redirect('cert_admin:historico')


@admin_required
def historico_zip_group_view(request):
    subject_code = request.GET.get('subject_code')
    professor_id = request.GET.get('professor_id')
    course_date = request.GET.get('course_date')
    certs = Certificate.objects.filter(
        subject_code=subject_code, professor_id=professor_id, course_date=course_date,
    )
    return _zip_response(certs, request, f'{subject_code}.zip')


@admin_required
def historico_zip_selected_view(request):
    ids = request.POST.getlist('ids')
    certs = Certificate.objects.filter(pk__in=ids)
    return _zip_response(certs, request, 'certificados.zip')


_IMPORT_SESSION_KEY = 'cert_import_rows'


@admin_required
def importar_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'cancel':
            request.session.pop(_IMPORT_SESSION_KEY, None)
            return redirect('cert_admin:importar')

        if action == 'upload' and request.FILES.get('spreadsheet'):
            rows, error = parse_spreadsheet(request.FILES['spreadsheet'])
            if error:
                messages.error(request, error)
                request.session.pop(_IMPORT_SESSION_KEY, None)
            else:
                request.session[_IMPORT_SESSION_KEY] = {
                    'filename': request.FILES['spreadsheet'].name,
                    'rows': [
                        {**row, 'course_date': row['course_date'].isoformat() if row['course_date'] else None}
                        for row in rows
                    ],
                }
            return redirect('cert_admin:importar')

        if action == 'confirm':
            staged = request.session.get(_IMPORT_SESSION_KEY)
            course_template = get_object_or_404(CourseTemplate, pk=request.POST.get('course_template'))
            professor = get_object_or_404(Professor, pk=request.POST.get('professor'))
            duration = request.POST.get('duration', '').strip()
            cert_type = request.POST.get('cert_type', 'interno')
            created = 0
            if staged:
                for row in staged['rows']:
                    if row['status'] != 'ok':
                        continue
                    StudentRegistration.objects.create(
                        student_name=row['student_name'],
                        cpf=row['cpf'],
                        course_template=course_template,
                        professor=professor,
                        created_by=request.user,
                        subject_code=row['subject_code'],
                        course_date=row['course_date'],
                        duration=duration,
                        cert_type=cert_type,
                    )
                    created += 1
            request.session.pop(_IMPORT_SESSION_KEY, None)
            messages.success(request, f'{created} cadastro(s) importado(s) e enviados para aprovação.')
            return redirect('cert_admin:importar')

    staged = request.session.get(_IMPORT_SESSION_KEY)
    ok_count = sum(1 for row in staged['rows'] if row['status'] == 'ok') if staged else 0
    return render(request, 'certificates/importar.html', _cert_context(
        'importar', staged=staged, ok_count=ok_count,
        course_templates=CourseTemplate.objects.all(), professors=Professor.objects.all(),
    ))


@admin_required
def modelos_view(request):
    editing = None
    edit_id = request.GET.get('edit')
    if edit_id:
        editing = get_object_or_404(CourseTemplate, pk=edit_id)

    if request.method == 'POST':
        instance = None
        post_edit_id = request.POST.get('editing_id')
        if post_edit_id:
            instance = get_object_or_404(CourseTemplate, pk=post_edit_id)
        form = CourseTemplateForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Modelo salvo com sucesso.')
            return redirect('cert_admin:modelos')
    else:
        form = CourseTemplateForm(instance=editing)

    templates = CourseTemplate.objects.all()
    return render(request, 'certificates/modelos.html', _cert_context(
        'modelos', form=form, templates=templates, editing=editing,
    ))


@admin_required
def modelo_remove_view(request, pk):
    template = get_object_or_404(CourseTemplate, pk=pk)
    if request.method == 'POST':
        try:
            template.delete()
            messages.success(request, 'Modelo removido.')
        except ProtectedError:
            messages.error(request, 'Não é possível remover: há certificados ou cadastros vinculados a este modelo.')
    return redirect('cert_admin:modelos')


@admin_required
def professor_remove_view(request, pk):
    professor = get_object_or_404(Professor, pk=pk)
    if request.method == 'POST':
        try:
            professor.delete()
            messages.success(request, 'Professor removido.')
        except ProtectedError:
            messages.error(request, 'Não é possível remover: há certificados ou cadastros vinculados a este professor.')
    return redirect('cert_admin:professores')


@admin_required
def configuracoes_view(request):
    settings_obj = CertificateSettings.load()
    if request.method == 'POST':
        form = CertificateSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configurações salvas.')
            return redirect('cert_admin:configuracoes')
    else:
        form = CertificateSettingsForm(instance=settings_obj)

    return render(request, 'certificates/configuracoes.html', _cert_context('configuracoes', form=form))
