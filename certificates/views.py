from django.shortcuts import render

from .models import Certificate


def verify_view(request):
    code = ''
    result = None
    checked = False

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        checked = True
        if code:
            result = Certificate.objects.filter(code__iexact=code).first()

    context = {
        'code': code,
        'checked': checked,
        'certificate': result,
    }
    return render(request, 'certificates/verify.html', context)
