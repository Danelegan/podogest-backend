from django.db import models


class Appointment(models.Model):
    """Reserva de una cita de podología."""

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
    service_type = models.CharField(
        max_length=30,
        choices=ServiceType.choices,
        default=ServiceType.GENERAL,
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['appointment_date', 'appointment_time']
        # Evita dos reservas en el mismo horario.
        constraints = [
            models.UniqueConstraint(
                fields=['appointment_date', 'appointment_time'],
                name='unique_appointment_slot',
            )
        ]

    def __str__(self):
        return f'{self.patient_name} - {self.appointment_date} {self.appointment_time:%H:%M}'
