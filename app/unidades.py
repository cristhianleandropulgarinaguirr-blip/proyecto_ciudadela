# app/unidades.py
# Las unidades privadas (apartamentos) del conjunto con su coeficiente: la BASE del quórum de una asamblea.
#
# Regla de oro: «Usuarios» sigue siendo la fuente para los apartamentos que tienen residentes en la app (el coeficiente se edita allí, como
# siempre). `sincronizar` copia esos datos a la tabla `unidades` y crea las que falten. Los propietarios SIN cuenta se registran a mano
# (origen «manual»); así el 100 % del conjunto cuenta para el quórum aunque no todos usen la app.
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.coeficientes import DECIMALES, TOLERANCIA, TOTAL_MAXIMO, norm_apto, por_apartamento, residentes_activos
from app.models import Unidad, Usuario


def residentes_por_unidad(db: Session) -> dict[str, list[Usuario]]:
    """{clave de apartamento: residentes activos}, ordenados por id (el primero es el «titular» que se muestra)."""
    mapa: dict[str, list[Usuario]] = {}
    for u in sorted(residentes_activos(db), key=lambda r: r.id):
        clave = norm_apto(u.apartamento)
        if clave:
            mapa.setdefault(clave, []).append(u)
    return mapa


def sincronizar(db: Session, _reintento: bool = True) -> None:
    """Crea y actualiza las unidades a partir de los residentes. Es idempotente y solo escribe si algo cambió. Hace commit al terminar."""
    grupos = residentes_por_unidad(db)
    coeficientes = por_apartamento([u for us in grupos.values() for u in us])
    existentes = {u.clave: u for u in db.query(Unidad).all()}
    hubo_cambios = False
    for clave, residentes in grupos.items():
        coef = coeficientes.get(clave)
        titular = residentes[0]
        unidad = existentes.get(clave)
        if unidad is None:
            db.add(Unidad(apartamento=titular.apartamento.strip(), clave=clave, coeficiente=coef, propietario_nombre=titular.nombre_completo[:120], origen="usuarios", activa=True))
            hubo_cambios = True
            continue
        if coef is not None and unidad.coeficiente != coef:
            unidad.coeficiente = coef
            hubo_cambios = True
        if unidad.propietario_nombre != titular.nombre_completo[:120]:
            unidad.propietario_nombre = titular.nombre_completo[:120]
            hubo_cambios = True
        if unidad.origen != "usuarios":
            unidad.origen = "usuarios"
            hubo_cambios = True
    if not hubo_cambios:
        return
    try:
        db.commit()
    except IntegrityError:            # otra petición creó la misma unidad a la vez: se descarta y se repite una sola vez
        db.rollback()
        if _reintento:
            sincronizar(db, _reintento=False)


def con_cuenta(db: Session) -> set[str]:
    return set(residentes_por_unidad(db).keys())


@dataclass
class ResumenUnidades:
    total: float = 0.0
    unidades: int = 0
    sin_coeficiente: list[str] = field(default_factory=list)
    sin_cuenta: int = 0

    @property
    def completo(self) -> bool:
        return self.unidades > 0 and not self.sin_coeficiente and abs(self.total - TOTAL_MAXIMO) <= 0.01

    @property
    def problema(self) -> Optional[str]:
        if self.unidades == 0:
            return "No hay unidades registradas."
        if self.sin_coeficiente:
            return f"Faltan coeficientes en: {', '.join(self.sin_coeficiente[:8])}{'…' if len(self.sin_coeficiente) > 8 else ''}."
        if abs(self.total - TOTAL_MAXIMO) > 0.01:
            return f"Los coeficientes suman {self.total:g} % y deben sumar 100 %."
        return None


def resumen(db: Session) -> ResumenUnidades:
    cuentas = con_cuenta(db)
    r = ResumenUnidades()
    for u in db.query(Unidad).filter(Unidad.activa.is_(True)).order_by(Unidad.id).all():
        r.unidades += 1
        if u.clave not in cuentas:
            r.sin_cuenta += 1
        if u.coeficiente is None or u.coeficiente <= 0:
            r.sin_coeficiente.append(u.apartamento)
        else:
            r.total += u.coeficiente
    r.total = round(r.total, DECIMALES)
    r.sin_coeficiente.sort()
    return r


def total_con(db: Session, sumar: float = 0.0, excluir_id: Optional[int] = None) -> float:
    """Suma de coeficientes de las unidades activas (para validar que no pase de 100 % al crear o editar una)."""
    q = db.query(Unidad).filter(Unidad.activa.is_(True))
    if excluir_id:
        q = q.filter(Unidad.id != excluir_id)
    return round(sum(u.coeficiente or 0.0 for u in q.all()) + sumar, DECIMALES)


def limite_superado(total: float) -> bool:
    return total > TOTAL_MAXIMO + TOLERANCIA


def en_mora(residentes: list[Usuario]) -> bool:
    """Una unidad está en mora si alguno de sus residentes figura sin estar al día o con saldo pendiente."""
    return any((not (r.esta_al_dia if r.esta_al_dia is not None else True)) or (r.saldo_pendiente or 0) > 0 for r in residentes)
