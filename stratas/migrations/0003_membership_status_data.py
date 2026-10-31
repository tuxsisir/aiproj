from django.db import migrations


def forwards(apps, schema_editor):
    Membership = apps.get_model('stratas', 'Membership')
    StrataInvitation = apps.get_model('stratas', 'StrataInvitation')
    # Existing members were already granted access, so they stay ACTIVE.
    Membership.objects.filter(is_active=True).update(status='ACTIVE')
    Membership.objects.filter(is_active=False).update(status='INACTIVE')
    # PRESIDENT used to be a role; it is now a council position.
    Membership.objects.filter(role='PRESIDENT').update(role='COUNCIL', position='PRESIDENT')
    StrataInvitation.objects.filter(role='PRESIDENT').update(role='COUNCIL')
    # Caretaker role is retired.
    Membership.objects.filter(role='CARETAKER').update(role='COUNCIL', status='INACTIVE')
    StrataInvitation.objects.filter(role='CARETAKER').delete()


def backwards(apps, schema_editor):
    Membership = apps.get_model('stratas', 'Membership')
    Membership.objects.filter(status='ACTIVE').update(is_active=True)
    Membership.objects.exclude(status='ACTIVE').update(is_active=False)
    Membership.objects.filter(position='PRESIDENT').update(role='PRESIDENT')


class Migration(migrations.Migration):

    dependencies = [
        ('stratas', '0002_membership_status_position'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
