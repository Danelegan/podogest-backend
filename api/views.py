import hmac

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Appointment, ClinicalRecord
from .serializers import AppointmentSerializer, ClinicalRecordSerializer
from .services import read_appointment_token, send_appointment_confirmation, send_due_reminders
from .throttles import ReservaBurstThrottle, ReservaSustainedThrottle


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer

    def get_permissions(self):
        # Agendar y consultar horarios ocupados es público; el resto exige autenticación.
        if self.action in ['create', 'horarios_ocupados']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        # Crear reservas es público: se añade un límite estricto contra spam/DoS
        # además del límite anónimo general. Los usuarios con JWT no se ven afectados.
        if self.action == 'create':
            return [*super().get_throttles(), ReservaBurstThrottle(), ReservaSustainedThrottle()]
        return super().get_throttles()

    @action(detail=False, methods=['get'], url_path='horarios-ocupados')
    def horarios_ocupados(self, request):
        # Solo fecha y hora, sin datos personales, para bloquearlas en el calendario.
        citas = (
            self.get_queryset()
            .exclude(status=Appointment.Status.CANCELLED)
            .values('appointment_date', 'appointment_time')
        )
        return Response(list(citas))

    def perform_create(self, serializer):
        appointment = serializer.save()
        send_appointment_confirmation(appointment)


class ClinicalRecordViewSet(viewsets.ModelViewSet):
    """Fichas podológicas: solo accesibles con JWT (uso exclusivo de la podóloga)."""

    queryset = ClinicalRecord.objects.select_related('appointment')
    serializer_class = ClinicalRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Permite buscar la ficha de una cita: /api/clinical-records/?appointment=<id>
        appointment_id = self.request.query_params.get('appointment')
        if appointment_id:
            queryset = queryset.filter(appointment_id=appointment_id)
        return queryset


# --- Enlaces del correo de recordatorio -------------------------------------
# Vistas HTML simples (fuera de DRF): el paciente no tiene JWT, el token firmado
# de la URL es lo que lo autoriza.

def _appointment_from_token(token):
    pk = read_appointment_token(token)
    if pk is None:
        return None
    return Appointment.objects.filter(pk=pk).first()


def _render_result(request, title, message, status=200):
    return render(request, 'citas/accion_cita.html', {
        'title': title,
        'message': message,
    }, status=status)


def _invalid_link(request):
    return _render_result(
        request,
        'Enlace no válido',
        'Este enlace no es válido o la cita ya no existe. Si necesitas ayuda, responde el correo que te enviamos.',
        status=404,
    )


def _past_appointment(request):
    return _render_result(
        request,
        'Cita finalizada',
        'Esta cita ya pasó, por lo que no es posible modificarla.',
        status=410,
    )


@require_GET
def confirmar_cita(request, token):
    appointment = _appointment_from_token(token)
    if appointment is None:
        return _invalid_link(request)
    if appointment.status == Appointment.Status.CANCELLED:
        return _render_result(
            request,
            'Cita cancelada',
            'Esta cita fue cancelada anteriormente. Si deseas asistir, agenda una nueva hora en nuestro sitio web.',
        )
    if appointment.starts_at <= timezone.now():
        return _past_appointment(request)

    if appointment.status != Appointment.Status.CONFIRMED:
        appointment.status = Appointment.Status.CONFIRMED
        appointment.save(update_fields=['status'])

    return _render_result(
        request,
        '¡Cita confirmada!',
        f'Gracias, {appointment.patient_name}. Te esperamos el {appointment.appointment_date:%d-%m-%Y} '
        f'a las {appointment.appointment_time:%H:%M}.',
    )


# El token firmado de la URL reemplaza la protección CSRF (no hay sesión que proteger).
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def cancelar_cita(request, token):
    appointment = _appointment_from_token(token)
    if appointment is None:
        return _invalid_link(request)
    if appointment.status == Appointment.Status.CANCELLED:
        return _render_result(request, 'Cita cancelada', 'Esta cita ya se encontraba cancelada.')
    if appointment.starts_at <= timezone.now():
        return _past_appointment(request)

    # GET solo pide confirmación: algunos filtros de correo abren los enlaces
    # automáticamente y no deben poder cancelar la cita por sí solos.
    if request.method == 'GET':
        return render(request, 'citas/accion_cita.html', {
            'title': '¿Cancelar tu cita?',
            'message': (
                f'{appointment.patient_name}, vas a cancelar tu cita del '
                f'{appointment.appointment_date:%d-%m-%Y} a las {appointment.appointment_time:%H:%M}.'
            ),
            'confirm_cancel': True,
        })

    appointment.status = Appointment.Status.CANCELLED
    appointment.save(update_fields=['status'])
    return _render_result(
        request,
        'Cita cancelada',
        'Tu cita fue cancelada correctamente. Puedes agendar una nueva hora cuando lo necesites.',
    )


# --- Endpoint para el cron externo (cron-job.org) ----------------------------

def _cron_token(request):
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth.removeprefix('Bearer ').strip()
    return request.headers.get('X-Cron-Token') or request.GET.get('token', '')


# Lo llama un servicio externo sin sesión: se protege con CRON_SECRET, no con CSRF.
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def cron_send_reminders(request):
    secret = settings.CRON_SECRET
    # Sin CRON_SECRET configurado el endpoint queda deshabilitado.
    # compare_digest evita filtrar el token midiendo el tiempo de respuesta.
    if not secret or not hmac.compare_digest(_cron_token(request).encode(), secret.encode()):
        return JsonResponse({'detail': 'No autorizado.'}, status=401)

    sent, due = send_due_reminders()
    return JsonResponse({'enviados': sent, 'pendientes': due})
