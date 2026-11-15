# app/coeficientes.py
# Coeficiente de copropiedad (Ley 675 de 2001): el porcentaje que cada apartamento «pesa» en las decisiones de la asamblea.
# Se guarda en PORCENTAJE (0,8523 = 0,8523 %) y la suma de todos los apartamentos del conjunto debe ser 100.
# Un apartamento puede tener varios usuarios Residente (por ejemplo dos copropietarios): el coeficiente es del APARTAMENTO, así que
# aquí se agrupa por apartamento (sin importar mayúsculas, tildes ni espacios de más) y se toma el mayor valor registrado.
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.constantes import RolNombre
from app.models import Rol, Usuario

TOTAL_MAXIMO = 100.0
TOLERANCIA = 0.0005          # lo que se acepta por encima de 100 (redondeos de la escritura de propiedad horizontal)
DECIMALES = 4


def norm_apto(apto: Optional[str]) -> str:
    t = unicodedata.normalize("NFKD", apto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def residentes_activos(db: Session) -> list[Usuario]:
    return (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id)
            .filter(Rol.nombre == RolNombre.RESIDENTE.value, Usuario.esta_activo.is_(True)).all())


def por_apartamento(residentes: list[Usuario], sustituir: Optional[tuple[int, Optional[float]]] = None) -> dict[str, Optional[float]]:
    """{apartamento normalizado: coeficiente}. `sustituir=(usuario_id, valor)` simula el cambio de un usuario sin guardarlo."""
    mapa: dict[str, Optional[float]] = {}
    for u in residentes:
        clave = norm_apto(u.apartamento)
        if not clave:
            continue
        valor = sustituir[1] if sustituir and sustituir[0] == u.id else u.coeficiente
        actual = mapa.get(clave)
        mapa[clave] = valor if actual is None else (actual if valor is None else max(actual, valor))
    return mapa


@dataclass
class Resumen:
    total: float = 0.0
    apartamentos: int = 0
    con_coeficiente: int = 0
    sin_coeficiente: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return self.apartamentos > 0 and not self.sin_coeficiente and abs(self.total - TOTAL_MAXIMO) <= 0.01


def resumen(db: Session) -> Resumen:
    residentes = residentes_activos(db)
    mapa = por_apartamento(residentes)
    nombres: dict[str, str] = {}
    for u in residentes:
        if norm_apto(u.apartamento):
            nombres.setdefault(norm_apto(u.apartamento), u.apartamento.strip())
    r = Resumen(apartamentos=len(mapa))
    for clave, valor in mapa.items():
        if valor is None or valor <= 0:
            r.sin_coeficiente.append(nombres[clave])
        else:
            r.con_coeficiente += 1
            r.total += valor
    r.total = round(r.total, DECIMALES)
    r.sin_coeficiente.sort()
    return r
