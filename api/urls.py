from rest_framework.routers import DefaultRouter

from .views import AppointmentViewSet, ClinicalRecordViewSet

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'clinical-records', ClinicalRecordViewSet, basename='clinical-record')

urlpatterns = router.urls
