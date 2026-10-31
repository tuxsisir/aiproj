# Split from 0002: Postgres can't alter a table with pending trigger events from the data migration.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stratas', '0003_membership_status_data'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='membership',
            name='stratas_mem_user_id_65b4cd_idx',
        ),
        migrations.RemoveField(
            model_name='membership',
            name='is_active',
        ),
        migrations.AlterField(
            model_name='membership',
            name='role',
            field=models.CharField(choices=[('COUNCIL', 'Council Member'), ('MANAGER', 'Strata Manager')], default='COUNCIL', max_length=20),
        ),
        migrations.AlterField(
            model_name='stratainvitation',
            name='role',
            field=models.CharField(choices=[('COUNCIL', 'Council Member'), ('MANAGER', 'Strata Manager')], max_length=20),
        ),
        migrations.AddIndex(
            model_name='membership',
            index=models.Index(fields=['user', 'status'], name='stratas_mem_user_id_7292b4_idx'),
        ),
        migrations.AddIndex(
            model_name='membership',
            index=models.Index(fields=['strata', 'status'], name='stratas_mem_strata__776661_idx'),
        ),
    ]
