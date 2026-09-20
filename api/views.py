import logging

from django.conf import settings
from django.core.mail import send_mail
from rest_framework import viewsets

from .models import Appointment
from .serializers import AppointmentSerializer

logger = logging.getLogger(__name__)


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer

    def perform_create(self, serializer):
        appointment = serializer.save()
        if appointment.email:
            self._send_confirmation(appointment)

    def _send_confirmation(self, appointment):
        subject = f'Confirmación de cita PodoGest - {appointment.appointment_date:%d-%m-%Y}'
        message = (
            f'Hola {appointment.patient_name},\n\n'
            'Tu cita ha sido agendada con éxito.\n\n'
            'Detalles de la reserva:\n'
            f'Fecha: {appointment.appointment_date:%d-%m-%Y}\n'
            f'Hora: {appointment.appointment_time:%H:%M}\n\n'
            'Te esperamos en la clínica. ¡Saludos!'
        )
        # Si el correo falla la cita igual queda guardada; solo se registra el error.
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[appointment.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Error al enviar el correo: {e}")