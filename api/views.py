import json
import logging
import os
import urllib.error
import urllib.request
from html import escape

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Appointment
from .serializers import AppointmentSerializer

logger = logging.getLogger(__name__)

RESEND_URL = 'https://api.resend.com/emails'


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer

    def get_permissions(self):
        # Cualquiera puede agendar (POST); ver, editar y borrar exige autenticación.
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        appointment = serializer.save()
        if appointment.email:
            self._send_confirmation(appointment)

    def _send_confirmation(self, appointment):
        # En la capa gratuita de Resend, 'from' debe ser onboarding@resend.dev
        # y 'to' solo puede ser el correo con el que te registraste en Resend.
        payload = {
            'from': 'PodoGest <onboarding@resend.dev>',
            'to': [appointment.email],
            'subject': f'Confirmación de cita PodoGest - {appointment.appointment_date:%d-%m-%Y}',
            'html': (
                f'<h3>Hola {escape(appointment.patient_name)},</h3>'
                '<p>Tu cita ha sido agendada con éxito.</p>'
                f'<p><strong>Fecha:</strong> {appointment.appointment_date:%d-%m-%Y}<br>'
                f'<strong>Hora:</strong> {appointment.appointment_time:%H:%M}</p>'
                '<p>Te esperamos en la clínica. ¡Saludos!</p>'
            ),
        }
        headers = {
            'Authorization': f'Bearer {os.environ.get("RESEND_API_KEY", "")}',
            'Content-Type': 'application/json',
            # Cloudflare (delante de Resend) bloquea el User-Agent por defecto de urllib (error 1010).
            'User-Agent': 'podogest-backend/1.0',
        }

        # Si el correo falla la cita igual queda guardada; solo se registra el error.
        try:
            req = urllib.request.Request(
                RESEND_URL,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                logger.info('Resend: %s', response.read())
        except urllib.error.HTTPError as e:
            # Resend explica en el cuerpo de la respuesta por qué rechazó la petición.
            logger.error(
                'Resend rechazó el correo (HTTP %s): %s',
                e.code,
                e.read().decode('utf-8', errors='replace'),
            )
        except Exception:
            logger.exception('Error al enviar el correo con Resend')
