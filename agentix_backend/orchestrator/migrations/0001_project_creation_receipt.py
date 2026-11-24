from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('companies', '0001_initial'),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectCreationReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('thread_id', models.CharField(max_length=255)),
                ('execution_id', models.CharField(max_length=255)),
                ('task_id', models.CharField(max_length=80)),
                ('operation_key', models.CharField(max_length=64)),
                ('canonical_payload', models.JSONField()),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('committed', 'Committed')],
                    default='pending',
                    max_length=16,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='project_creation_receipts',
                    to='companies.company',
                )),
                ('project', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='creation_receipt',
                    to='projects.project',
                )),
            ],
            options={'db_table': 'project_creation_receipts'},
        ),
        migrations.AddConstraint(
            model_name='projectcreationreceipt',
            constraint=models.UniqueConstraint(
                fields=('company', 'operation_key'),
                name='unique_company_project_creation_operation',
            ),
        ),
    ]
