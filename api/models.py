from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.db.models import Q


class Appointment(models.Model):
    """Reserva de una cita de podología."""

    class Status(models.TextChoices):
        PENDING = 'pendiente', 'Pendiente'
        CONFIRMED = 'confirmada', 'Confirmada'
        CANCELLED = 'cancelada', 'Cancelada'

    class ServiceType(models.TextChoices):
        GENERAL = 'general', 'Consulta podológica general'
        QUIROPODIA = 'quiropodia', 'Quiropodia (atención de callos y durezas)'
        ONYCHOCRYPTOSIS = 'uña_encarnada', 'Tratamiento de uña encarnada'
        ONYCHOMYCOSIS = 'hongos', 'Tratamiento de hongos (onicomicosis)'
        DIABETIC_FOOT = 'pie_diabetico', 'Atención de pie diabético'
        PLANTAR_WARTS = 'verrugas', 'Tratamiento de verrugas plantares'

    patient_name = models.CharField(max_length=150)
    rut = models.CharField(max_length=12)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    service_type = models.CharField(
        max_length=150,
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Se marca al enviar el recordatorio para no repetirlo en la siguiente ejecución del cron.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['appointment_date', 'appointment_time']
        # Evita dos reservas en el mismo horario (las canceladas liberan el horario).
        constraints = [
            models.UniqueConstraint(
                fields=['appointment_date', 'appointment_time'],
                condition=~Q(status='cancelada'),
                name='unique_appointment_slot',
            )
        ]

    def __str__(self):
        return f'{self.patient_name} - {self.appointment_date} {self.appointment_time:%H:%M}'

    @property
    def starts_at(self):
        """Fecha y hora de la cita como datetime aware en la zona horaria de la clínica."""
        return datetime.combine(
            self.appointment_date,
            self.appointment_time,
            tzinfo=ZoneInfo(settings.CLINIC_TIME_ZONE),
        )


class ClinicalRecord(models.Model):
    """Ficha podológica: evaluación clínica asociada a una cita."""

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='clinical_record',
    )
    antecedentes_medicos = models.TextField(blank=True, null=True)
    sintomas = models.TextField(blank=True, null=True)
    diagnostico = models.TextField(blank=True, null=True)
    tratamiento_realizado = models.TextField(blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Ficha de {self.appointment.patient_name} ({self.appointment.appointment_date})'
