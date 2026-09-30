import re

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import professor_required
from .forms import StudentRegistrationForm
from .models import CourseTemplate, StudentRegistration


def _duration_number(duration_text):
    """Extracts the leading number from a stored duration string like '7 HORAS'."""
    match = re.match(r'\s*(\d+)', duration_text or '')
    return int(match.group(1)) if match else None


@professor_required
def folders_view(request):
    counts = {
        row['course_template']: row['n']
        for row in StudentRegistration.objects.filter(created_by=request.user)
        .values('course_template').annotate(n=Count('id'))
    }
    items = [
        {'template': template, 'count': counts.get(template.id, 0)}
        for template in CourseTemplate.objects.all()
    ]
    return render(request, 'certificates/prof_folders.html', {
        'items': items,
        'active_nav': 'certificados_prof',
    })


@professor_required
def groups_view(request, template_id):
    template = get_object_or_404(CourseTemplate, pk=template_id)
    regs = StudentRegistration.objects.filter(course_template=template, created_by=request.user)
    groups = {}
    for reg in regs:
        key = (reg.subject_code, reg.course_date)
        groups.setdefault(key, {'subject_code': reg.subject_code, 'course_date': reg.course_date, 'count': 0})
        groups[key]['count'] += 1
    group_list = sorted(groups.values(), key=lambda g: g['course_date'], reverse=True)
    return render(request, 'certificates/prof_groups.html', {
        'template': template,
        'groups': group_list,
        'active_nav': 'certificados_prof',
    })


@professor_required
def form_view(request, template_id):
    template = get_object_or_404(CourseTemplate, pk=template_id)
    subject_code = request.GET.get('subject_code', '').strip()
    course_date = request.GET.get('course_date', '').strip()

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            StudentRegistration.objects.create(
                student_name=data['student_name'],
                cpf=data['cpf'],
                course_template=template,
                professor=data['professor'],
                created_by=request.user,
                subject_code=data['subject_code'],
                client_name=data['client_name'],
                course_date=data['course_date'],
                duration=f"{data['duration']} HORAS",
                cert_type=data['cert_type'],
            )
            messages.success(request, 'Aluno cadastrado. Aguardando aprovação do administrador.')
            url = reverse('cert_prof:form', args=[template.pk])
            return redirect(f'{url}?subject_code={data["subject_code"]}&course_date={data["course_date"]}')
    else:
        initial = {}
        prior = None
        if subject_code and course_date:
            initial['subject_code'] = subject_code
            initial['course_date'] = course_date
            prior = StudentRegistration.objects.filter(
                course_template=template, subject_code=subject_code,
                course_date=course_date, created_by=request.user,
            ).order_by('-created_at').first()
        if prior:
            initial['professor'] = prior.professor_id
            initial['duration'] = _duration_number(prior.duration)
            initial['cert_type'] = prior.cert_type
            initial['client_name'] = prior.client_name
        form = StudentRegistrationForm(initial=initial)

    registrations = StudentRegistration.objects.filter(course_template=template, created_by=request.user)
    if subject_code:
        registrations = registrations.filter(subject_code=subject_code)
    if course_date:
        registrations = registrations.filter(course_date=course_date)
    registrations = registrations.order_by('-created_at')

    return render(request, 'certificates/prof_form.html', {
        'template': template,
        'form': form,
        'subject_code': subject_code,
        'course_date': course_date,
        'registrations': registrations,
        'active_nav': 'certificados_prof',
    })
