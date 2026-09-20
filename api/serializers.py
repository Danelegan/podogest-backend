from rest_framework import serializers

from .models import Appointment, ClinicalRecord


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = '__all__'
        read_only_fields = ['created_at']
        # Se desactiva el validador automático de la UniqueConstraint del modelo
        # para que validate() entregue el mensaje personalizado.
        validators = []

    def validate(self, attrs):
        date = attrs.get('appointment_date', getattr(self.instance, 'appointment_date', None))
        time = attrs.get('appointment_time', getattr(self.instance, 'appointment_time', None))

        taken = Appointment.objects.filter(appointment_date=date, appointment_time=time)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)

        if taken.exists():
            raise serializers.ValidationError(
                'Lo sentimos, este horario ya fue reservado por otro paciente.'
            )
        return attrs


class ClinicalRecordSerializer(serializers.ModelSerializer):
    # Datos de solo lectura de la cita para mostrar la ficha sin otra consulta.
    patient_name = serializers.CharField(source='appointment.patient_name', read_only=True)
    appointment_date = serializers.DateField(source='appointment.appointment_date', read_only=True)
    appointment_time = serializers.TimeField(source='appointment.appointment_time', read_only=True)

    class Meta:
        model = ClinicalRecord
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
