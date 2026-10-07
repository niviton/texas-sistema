from django.db import migrations, models


def vistoriador_para_tecnico(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='vistoriador').update(role='tecnico')


def tecnico_para_vistoriador(apps, schema_editor):
    pass  # não há como saber quem era vistoriador; reverter mantém Técnico


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(vistoriador_para_tecnico, tecnico_para_vistoriador),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Administrador'), ('tecnico', 'Técnico (executor de checklists)'), ('logistica', 'Logística'), ('professor', 'Professor')], default='professor', max_length=20),
        ),
    ]
