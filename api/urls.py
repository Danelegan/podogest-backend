from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AppointmentViewSet,
    ClinicalRecordViewSet,
    cancelar_cita,
    confirmar_cita,
    cron_send_reminders,
)

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'clinical-records', ClinicalRecordViewSet, basename='clinical-record')

urlpatterns = [
    # Enlaces del correo de recordatorio (token firmado, ver services.py).
    path('citas/<str:token>/confirmar/', confirmar_cita, name='confirmar_cita'),
    path('citas/<str:token>/cancelar/', cancelar_cita, name='cancelar_cita'),
    # Lo llama cron-job.org periódicamente (protegido con CRON_SECRET).
    path('cron/send-reminders/', cron_send_reminders, name='cron_send_reminders'),
    *router.urls,
]
