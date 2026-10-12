from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle


class ReservaBurstThrottle(AnonRateThrottle):
    """Frena ráfagas de reservas anónimas desde una misma IP (spam / DoS)."""

    scope = 'reservas_burst'


class ReservaSustainedThrottle(AnonRateThrottle):
    """Limita el total de reservas anónimas por hora desde una misma IP."""

    scope = 'reservas_sustained'


# ScopedRateThrottle lee el scope de un atributo de la vista; cada clase usa
# uno distinto para que la vista de login tenga dos límites a la vez.

class LoginBurstThrottle(ScopedRateThrottle):
    """Frena la fuerza bruta al login: pocos intentos seguidos por IP."""

    scope_attr = 'throttle_scope_burst'


class LoginSustainedThrottle(ScopedRateThrottle):
    """Limita el total de intentos de login por hora desde una misma IP."""

    scope_attr = 'throttle_scope_sustained'
