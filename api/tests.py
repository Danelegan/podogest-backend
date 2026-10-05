from datetime import date, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Appointment, ClinicalRecord
from api.services import make_appointment_token


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


@override_settings(CRON_SECRET='secreto-de-prueba')
class RecordatorioTests(TestCase):
    def crear_cita(self, en_horas, **extra):
        from api.models import Appointment
        inicio = timezone.localtime(
            timezone.now() + timedelta(hours=en_horas),
            ZoneInfo(settings.CLINIC_TIME_ZONE),
        )
        datos = {
            'patient_name': 'Paciente Prueba',
            'rut': '11111111-1',
            'phone': '+56911111111',
            'email': 'paciente@example.com',
            'service_type': 'general',
            'appointment_date': inicio.date(),
            'appointment_time': inicio.time().replace(second=0, microsecond=0),
        }
        datos.update(extra)
        return Appointment.objects.create(**datos)

    @patch('api.services.resend.Emails.send', return_value={'id': 'test'})
    def test_envia_solo_citas_dentro_de_3_horas_y_una_vez(self, send):
        cita = self.crear_cita(2.5)
        self.crear_cita(5)  # demasiado lejos
        self.crear_cita(1, email='')  # sin correo
        self.crear_cita(2, status='cancelada')

        url = reverse('cron_send_reminders')
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer secreto-de-prueba')
        self.assertEqual(response.json(), {'enviados': 1, 'pendientes': 1})
        response = self.client.get(url, {'token': 'secreto-de-prueba'})
        self.assertEqual(response.json(), {'enviados': 0, 'pendientes': 0})

        self.assertEqual(send.call_count, 1)
        params = send.call_args.args[0]
        self.assertEqual(params['to'], ['paciente@example.com'])
        self.assertEqual(params['from'], 'PasosSaludables <contacto@pasossaludables.cl>')
        self.assertIn('Hola <strong>Paciente Prueba</strong>', params['html'])
        self.assertIn(reverse('confirmar_cita', args=[make_appointment_token(cita)]), params['html'])
        cita.refresh_from_db()
        self.assertIsNotNone(cita.reminder_sent_at)

    def test_confirmar(self):
        cita = self.crear_cita(2)
        response = self.client.get(reverse('confirmar_cita', args=[make_appointment_token(cita)]))
        self.assertEqual(response.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'confirmada')

    def test_cancelar_requiere_post_y_libera_el_horario(self):
        cita = self.crear_cita(2)
        url = reverse('cancelar_cita', args=[make_appointment_token(cita)])

        self.client.get(url)
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'pendiente')

        self.client.post(url)
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'cancelada')
        # El horario cancelado se puede volver a reservar.
        self.crear_cita(2, appointment_date=cita.appointment_date, appointment_time=cita.appointment_time)

    def test_cancelar_elimina_la_ficha_vacia(self):
        cita = self.crear_cita(2)
        ClinicalRecord.objects.create(appointment=cita, observaciones='   ')
        self.client.post(reverse('cancelar_cita', args=[make_appointment_token(cita)]))
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'cancelada')
        self.assertFalse(ClinicalRecord.objects.filter(appointment=cita).exists())

    def test_cancelar_conserva_la_ficha_con_datos(self):
        cita = self.crear_cita(2)
        ClinicalRecord.objects.create(appointment=cita, antecedentes_medicos='Diabetes tipo 2')
        self.client.post(reverse('cancelar_cita', args=[make_appointment_token(cita)]))
        cita.refresh_from_db()
        self.assertEqual(cita.status, 'cancelada')
        self.assertTrue(ClinicalRecord.objects.filter(appointment=cita).exists())

    def test_token_invalido(self):
        cita = self.crear_cita(2)
        response = self.client.get(reverse('confirmar_cita', args=[f'{cita.pk}:falso']))
        self.assertEqual(response.status_code, 404)

    @patch('api.services.resend.Emails.send')
    def test_cron_rechaza_token_incorrecto_o_ausente(self, send):
        self.crear_cita(2)
        url = reverse('cron_send_reminders')
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, {'token': 'otro'}).status_code, 401)
        send.assert_not_called()

    @override_settings(CRON_SECRET='')
    def test_cron_deshabilitado_sin_secreto(self):
        response = self.client.get(reverse('cron_send_reminders'), {'token': ''})
        self.assertEqual(response.status_code, 401)


class AtencionEspontaneaTests(TestCase):
    url = '/api/appointments/atencion-espontanea/'
    datos = {
        'patient_name': 'Paciente Espontáneo',
        'rut': '22222222-2',
        'phone': '+56922222222',
        'email': 'espontaneo@example.com',
    }

    def setUp(self):
        self.client = APIClient()

    def test_requiere_autenticacion(self):
        response = self.client.post(self.url, self.datos, format='json')
        self.assertEqual(response.status_code, 401)

    @patch('api.services.resend.Emails.send')
    def test_crea_cita_ahora_y_su_ficha(self, send):
        self.client.force_authenticate(User.objects.create_user('podologa'))
        response = self.client.post(self.url, self.datos, format='json')
        self.assertEqual(response.status_code, 201)

        cita = Appointment.objects.get(pk=response.data['appointment']['id'])
        self.assertEqual(cita.status, 'confirmada')
        self.assertEqual(cita.service_type, 'general')
        self.assertLess(abs((timezone.now() - cita.starts_at).total_seconds()), 5)
        self.assertEqual(response.data['clinical_record']['id'], cita.clinical_record.pk)
        send.assert_not_called()

    def test_datos_invalidos_no_crean_nada(self):
        self.client.force_authenticate(User.objects.create_user('podologa'))
        response = self.client.post(self.url, {**self.datos, 'email': 'no-es-correo'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Appointment.objects.exists())


class EliminarCitaTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cita = Appointment.objects.create(
            patient_name='Paciente Prueba', rut='11111111-1', phone='+56911111111',
            service_type='general', appointment_date=date(2030, 1, 7), appointment_time=time(10, 0),
        )
        ClinicalRecord.objects.create(appointment=self.cita, diagnostico='Onicomicosis')
        self.url = f'/api/appointments/{self.cita.pk}/'

    def test_requiere_autenticacion(self):
        self.assertEqual(self.client.delete(self.url).status_code, 401)
        self.assertTrue(Appointment.objects.exists())

    def test_elimina_la_cita_y_su_ficha(self):
        self.client.force_authenticate(User.objects.create_user('podologa'))
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(ClinicalRecord.objects.exists())


class CancelarDesdePanelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('podologa'))
        self.cita = Appointment.objects.create(
            patient_name='Paciente Prueba', rut='11111111-1', phone='+56911111111',
            service_type='general', appointment_date=date(2030, 1, 7), appointment_time=time(10, 0),
        )
        self.url = f'/api/appointments/{self.cita.pk}/'

    def test_cancelar_elimina_la_ficha_vacia(self):
        ClinicalRecord.objects.create(appointment=self.cita)
        response = self.client.patch(self.url, {'status': 'cancelada'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.status, 'cancelada')
        self.assertFalse(ClinicalRecord.objects.exists())

    def test_cancelar_conserva_la_ficha_con_datos(self):
        ClinicalRecord.objects.create(appointment=self.cita, sintomas='Dolor al caminar')
        self.client.patch(self.url, {'status': 'cancelada'}, format='json')
        self.assertTrue(ClinicalRecord.objects.exists())

    def test_otros_cambios_no_tocan_la_ficha(self):
        ClinicalRecord.objects.create(appointment=self.cita)
        self.client.patch(self.url, {'status': 'confirmada'}, format='json')
        self.assertTrue(ClinicalRecord.objects.exists())
