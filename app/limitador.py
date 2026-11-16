# app/limitador.py
# Freno contra abuso para las rutas SIN sesión (la página pública del pase) y contra adivinar PIN en portería.
# Vive en la memoria del proceso: no usa base de datos (sería una consulta más en cada petición) y se reinicia con el servidor.
# Con varios procesos cada uno cuenta aparte; para un conjunto en un solo servicio es suficiente. Si algún día hay varias
# instancias, este es el único archivo que habría que cambiar por Redis.
import threading
import time
from collections import deque
from typing import Hashable

_TODOS: list["Ventana"] = []


class Ventana:
    """«Máximo N eventos por ventana de S segundos» por cada clave (IP, id de usuario…)."""

    def __init__(self, maximo: int, segundos: int):
        self.maximo, self.segundos = maximo, segundos
        self._eventos: dict[Hashable, deque] = {}
        self._cerrojo = threading.Lock()
        self._ultima_limpieza = time.monotonic()
        _TODOS.append(self)

    def _purgar(self, cola: deque, ahora: float) -> None:
        while cola and ahora - cola[0] > self.segundos:
            cola.popleft()

    def _limpiar_viejas(self, ahora: float) -> None:
        """Cada minuto borra las claves sin actividad para que el diccionario no crezca sin fin."""
        if ahora - self._ultima_limpieza < 60:
            return
        self._ultima_limpieza = ahora
        for clave in [k for k, c in self._eventos.items() if not c or ahora - c[-1] > self.segundos]:
            del self._eventos[clave]

    def agotada(self, clave: Hashable) -> bool:
        """¿Esta clave ya llegó al tope? No cuenta nada."""
        with self._cerrojo:
            ahora = time.monotonic()
            cola = self._eventos.get(clave)
            if cola is None:
                return False
            self._purgar(cola, ahora)
            return len(cola) >= self.maximo

    def registrar(self, clave: Hashable) -> None:
        with self._cerrojo:
            ahora = time.monotonic()
            self._limpiar_viejas(ahora)
            cola = self._eventos.setdefault(clave, deque())
            self._purgar(cola, ahora)
            cola.append(ahora)

    def intentar(self, clave: Hashable) -> bool:
        """Cuenta el evento y dice si todavía estaba permitido (False = pasó el tope)."""
        if self.agotada(clave):
            return False
        self.registrar(clave)
        return True

    def olvidar(self, clave: Hashable) -> None:
        with self._cerrojo:
            self._eventos.pop(clave, None)

    def reiniciar(self) -> None:
        with self._cerrojo:
            self._eventos.clear()


def reiniciar_todo() -> None:
    """Para las pruebas: cada prueba empieza con los contadores en cero."""
    for v in _TODOS:
        v.reiniciar()


# Página pública del pase: leer (la página consulta cada ~20 s) y avisar («estoy en camino» / «llegué»).
LECTURAS_PUBLICAS = Ventana(maximo=90, segundos=60)
AVISOS_PUBLICOS = Ventana(maximo=10, segundos=60)
# PIN de portería: solo cuentan los FALLOS; 8 en 10 minutos bloquea al guardia unos minutos (1 millón de combinaciones).
PIN_FALLIDOS = Ventana(maximo=8, segundos=600)
# V4.0 · «Solicitar demo» de la landing (sin sesión): máximo 5 envíos por IP cada 10 minutos.
SOLICITUDES_DEMO = Ventana(maximo=5, segundos=600)
