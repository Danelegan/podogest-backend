import logging
import os
from html import escape

import resend

logger = logging.getLogger(__name__)

# Mientras el dominio propio se verifica en Resend se usa su remitente de pruebas.
# En ese modo 'to' solo puede ser el correo con el que te registraste en Resend.
FROM_EMAIL = 'PodoGest <onboarding@resend.dev>'


def send_appointment_confirmation(appointment):
    """Envía al paciente el correo de confirmación de su cita.

    Devuelve True si Resend aceptó el correo. Nunca lanza excepciones: si el
    envío falla la cita ya está guardada, así que solo se registra el error.
    """
    if not appointment.email:
        return False

    resend.api_key = os.environ.get('RESEND_API_KEY', '')
    fecha = f'{appointment.appointment_date:%d-%m-%Y}'
    hora = f'{appointment.appointment_time:%H:%M}'

    params: resend.Emails.SendParams = {
        'from': FROM_EMAIL,
        'to': [appointment.email],
        'subject': f'Confirmación de cita PodoGest - {fecha}',
        'html': (
            f'<h3>Hola {escape(appointment.patient_name)},</h3>'
            '<p>Tu cita ha sido agendada con éxito.</p>'
            f'<p><strong>Fecha:</strong> {fecha}<br>'
            f'<strong>Hora:</strong> {hora}</p>'
            '<p>Te esperamos en la clínica. ¡Saludos!</p>'
        ),
    }

    try:
        email = resend.Emails.send(params)
    except Exception:
        logger.exception('Error al enviar el correo de confirmación con Resend')
        return False

    logger.info('Resend: correo de confirmación enviado (id=%s)', email.get('id'))
    return True
