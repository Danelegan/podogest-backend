from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Appointment, ClinicalRecord
from .serializers import AppointmentSerializer, ClinicalRecordSerializer
from .services import send_appointment_confirmation
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
        citas = self.get_queryset().values('appointment_date', 'appointment_time')
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
