from django.contrib import admin

from .models import Certificate, CertificateSettings, CourseTemplate, Professor, StudentRegistration


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['code', 'student_name', 'course_title', 'instructor_name', 'issue_date']
    search_fields = ['code', 'student_name']


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'sigla', 'is_chief', 'chief_cert_type']
    list_filter = ['is_chief', 'chief_cert_type']
    search_fields = ['full_name', 'sigla']
    fields = [
        'full_name', 'sigla', 'signature', 'is_chief', 'chief_cert_type',
        'signature_offset_x_pt', 'signature_offset_y_pt',
        'signature_light_threshold', 'signature_dark_threshold', 'signature_invert_colors',
    ]


@admin.register(CourseTemplate)
class CourseTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'default_subject_number', 'default_duration']
    search_fields = ['title']


@admin.register(StudentRegistration)
class StudentRegistrationAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'subject_code', 'course_template', 'professor', 'status', 'created_at']
    list_filter = ['status', 'course_template', 'professor']
    search_fields = ['student_name', 'cpf', 'subject_code']


@admin.register(CertificateSettings)
class CertificateSettingsAdmin(admin.ModelAdmin):
    list_display = ['show_qr_code', 'signature_width_pt', 'signature_height_pt']

    def has_add_permission(self, request):
        return not CertificateSettings.objects.exists()
