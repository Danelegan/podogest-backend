import logging
import os
from datetime import timedelta
from html import escape

import resend
from django.conf import settings
from django.core import signing
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Appointment

logger = logging.getLogger(__name__)

# Remitente único de todos los correos al paciente (confirmación y recordatorio).
# Debe pertenecer a un dominio verificado en Resend (pasossaludables.cl).
FROM_EMAIL = 'PasosSaludables <contacto@pasossaludables.cl>'
# Si el paciente responde el correo, la respuesta llega a este buzón.
REPLY_TO = 'arokelina@gmail.com'


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
        'reply_to': REPLY_TO,
        'subject': f'Confirmación de cita PasosSaludables - {fecha}',
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


# Los enlaces de confirmar/cancelar llevan el id de la cita firmado con SECRET_KEY,
# así nadie puede modificar la cita de otro paciente cambiando el número en la URL.
TOKEN_SALT = 'api.appointment-reminder'


def make_appointment_token(appointment):
    return signing.dumps(appointment.pk, salt=TOKEN_SALT)


def read_appointment_token(token):
    """Devuelve el id de la cita del token, o None si el token no es válido."""
    try:
        return signing.loads(token, salt=TOKEN_SALT)
    except signing.BadSignature:
        return None


def send_appointment_reminder(appointment):
    """Envía al paciente el recordatorio de su cita con enlaces para confirmar o cancelar.

    Devuelve True si Resend aceptó el correo. Nunca lanza excepciones.
    """
    if not appointment.email:
        return False

    resend.api_key = os.environ.get('RESEND_API_KEY', '')
    token = make_appointment_token(appointment)
    fecha = f'{appointment.appointment_date:%d-%m-%Y}'

    # Las plantillas de Django escapan las variables automáticamente.
    html = render_to_string('emails/recordatorio_cita.html', {
        'nombre_paciente': appointment.patient_name,
        'fecha_cita': fecha,
        'hora_cita': f'{appointment.appointment_time:%H:%M}',
        'link_confirmar': settings.SITE_URL + reverse('confirmar_cita', args=[token]),
        'link_cancelar': settings.SITE_URL + reverse('cancelar_cita', args=[token]),
    })

    params: resend.Emails.SendParams = {
        'from': FROM_EMAIL,
        'to': [appointment.email],
        'reply_to': REPLY_TO,
        'subject': f'Recordatorio de tu cita en PasosSaludables - {fecha} {appointment.appointment_time:%H:%M}',
        'html': html,
    }

    try:
        email = resend.Emails.send(params)
    except Exception:
        logger.exception('Error al enviar el recordatorio con Resend (cita id=%s)', appointment.pk)
        return False

    logger.info('Resend: recordatorio enviado (cita id=%s, email id=%s)', appointment.pk, email.get('id'))
    return True


REMINDER_HOURS = 3


def send_due_reminders():
    """Envía el recordatorio a las citas que empiezan en las próximas REMINDER_HOURS horas.

    Se toman todas las citas que empiezan antes del límite y aún no tienen
    recordatorio, así una ejecución fallida o atrasada no deja a nadie sin correo;
    reminder_sent_at evita enviarlo dos veces. Devuelve (enviados, pendientes).
    """
    now = timezone.now()
    limit = now + timedelta(hours=REMINDER_HOURS)

    # El rango de fechas es amplio (±1 día) para cubrir la diferencia UTC/Chile;
    # el filtro exacto por hora se hace después con starts_at.
    candidates = (
        Appointment.objects
        .exclude(status=Appointment.Status.CANCELLED)
        .exclude(email='')
        .filter(reminder_sent_at__isnull=True)
        .filter(appointment_date__range=(
            (now - timedelta(days=1)).date(),
            (limit + timedelta(days=1)).date(),
        ))
    )
    due = [a for a in candidates if now < a.starts_at <= limit]

    sent = 0
    for appointment in due:
        if send_appointment_reminder(appointment):
            appointment.reminder_sent_at = timezone.now()
            appointment.save(update_fields=['reminder_sent_at'])
            sent += 1
    return sent, len(due)
