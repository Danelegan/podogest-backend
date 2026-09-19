from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "patient_name",
        "rut",
        "appointment_date",
        "appointment_time",
        "service_type",
    )
    search_fields = ("patient_name", "rut")
    list_filter = ("appointment_date", "service_type")
