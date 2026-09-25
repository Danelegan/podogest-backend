from rest_framework.throttling import AnonRateThrottle


class ReservaBurstThrottle(AnonRateThrottle):
    """Frena ráfagas de reservas anónimas desde una misma IP (spam / DoS)."""

    scope = 'reservas_burst'


class ReservaSustainedThrottle(AnonRateThrottle):
    """Limita el total de reservas anónimas por hora desde una misma IP."""

    scope = 'reservas_sustained'
