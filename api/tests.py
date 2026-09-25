from datetime import date, time

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient


def reserva(hour):
    return {
        'patient_name': 'Paciente Prueba',
        'rut': '11111111-1',
        'phone': '+56911111111',
        'service_type': 'general',
        'appointment_date': date(2030, 1, 7).isoformat(),
        'appointment_time': time(hour, 0).isoformat(),
    }


class ReservaThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_reservas_anonimas_limitadas_a_5_por_minuto(self):
        for hour in range(9, 14):
            response = self.client.post('/api/appointments/', reserva(hour), format='json')
            self.assertEqual(response.status_code, 201)

        response = self.client.post('/api/appointments/', reserva(14), format='json')
        self.assertEqual(response.status_code, 429)

    def test_horarios_ocupados_no_usa_el_limite_de_reservas(self):
        for _ in range(10):
            response = self.client.get('/api/appointments/horarios-ocupados/')
            self.assertEqual(response.status_code, 200)

    def test_usuario_autenticado_no_tiene_limite_de_reservas(self):
        user = User.objects.create_user('podologa', password='clave-segura-123')
        self.client.force_authenticate(user)
        for hour in range(9, 16):
            response = self.client.post('/api/appointments/', reserva(hour), format='json')
            self.assertEqual(response.status_code, 201)


class CorsTests(TestCase):
    def preflight(self, origin):
        return self.client.options(
            '/api/appointments/',
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        )

    def test_origen_permitido(self):
        response = self.preflight('https://podogest-frontend.vercel.app')
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Origin'),
            'https://podogest-frontend.vercel.app',
        )

    def test_origen_no_permitido(self):
        response = self.preflight('https://sitio-malicioso.com')
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)
