# tests/test_v36_importacion.py — Versión 3.6, Fase 2: carga masiva por Excel/CSV (censo de residentes y cartera).
import io

import pytest
from openpyxl import Workbook, load_workbook

from app.importacion import parsear_dinero
from app.models import Auditoria, Usuario

CLAVE = "claveSegura123"
XLSX = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def xlsx(filas, hoja_titulo=None):
    libro = Workbook()
    ws = libro.active
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    libro.save(buf)
    return buf.getvalue()


def subir(client, auth, tipo, datos, nombre="planilla.xlsx", accion="vista-previa", quien="admin@conjunto.com", **params):
    return client.post(f"/importaciones/{tipo}/{accion}", params=params, files={"archivo": (nombre, datos, XLSX)}, headers=auth(quien))


CENSO = [["nombre_completo", "email", "apartamento", "parqueadero", "valor_administracion"],
         ["Marta Rojas", "marta@correo.com", "Torre 3 Apt 301", "P-7", "180000"],
         ["Pedro Díaz", "PEDRO@correo.com", "Torre 3 Apt 302", None, None],
         ["Ana Residente Nueva", "ana@conjunto.com", "Torre 1 Apt 101", "P-1", 200000]]          # ana ya existe → actualizar


# ---------------------------------------------------------------- unidades del lector
@pytest.mark.parametrize("texto,esperado", [("$ 1.250.000", 1250000), ("1,250,000", 1250000), ("1250000.00", 1250000), ("150.000", 150000),
                                            ("150,000", 150000), ("0", 0), (1250000.0, 1250000), ("1.250,50", 1250), ("COP 90.000", 90000)])
def test_el_lector_de_dinero_entiende_formatos_colombianos(texto, esperado):
    assert parsear_dinero(texto) == esperado


@pytest.mark.parametrize("malo", ["", "abc", "-5", "(1.000)", "1.2.3", "99999999999"])
def test_el_lector_de_dinero_rechaza_basura_y_negativos(malo):
    with pytest.raises(ValueError):
        parsear_dinero(malo)


# ---------------------------------------------------------------- plantillas y permisos
def test_las_plantillas_se_descargan_con_sus_encabezados(client, auth):
    for tipo, cols in (("residentes", ["nombre_completo", "email", "apartamento", "parqueadero", "valor_administracion", "coeficiente"]), ("cartera", ["email", "apartamento", "saldo_pendiente"])):
        r = client.get(f"/importaciones/plantilla/{tipo}", headers=auth("admin@conjunto.com"))
        assert r.status_code == 200 and r.headers["content-type"] == XLSX
        libro = load_workbook(io.BytesIO(r.content))
        assert [c.value for c in libro["Datos"][1]] == cols and "Instrucciones" in libro.sheetnames
        assert libro["Datos"].max_row == 1               # sin filas de ejemplo que se importen por accidente


def test_solo_el_administrador_importa(client, auth):
    assert client.get("/importaciones/plantilla/cartera", headers=auth("ana@conjunto.com")).status_code == 403
    assert subir(client, auth, "residentes", xlsx(CENSO), quien="ana@conjunto.com").status_code == 403
    assert subir(client, auth, "cartera", xlsx(CENSO), quien="celador@conjunto.com", accion="aplicar").status_code == 403
    assert client.post("/importaciones/residentes/vista-previa", files={"archivo": ("a.xlsx", b"x", XLSX)}).status_code == 401
    assert client.get("/importaciones/plantilla/otra", headers=auth("admin@conjunto.com")).status_code == 422


# ---------------------------------------------------------------- censo de residentes
def test_vista_previa_dice_que_se_crea_y_que_se_actualiza_sin_guardar_nada(client, auth, db):
    antes = db.query(Usuario).count()
    r = subir(client, auth, "residentes", xlsx(CENSO))
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["total"], j["crear"], j["actualizar"], j["errores"], j["aplicado"]) == (3, 2, 1, 0, False) and j["credenciales"] == []
    assert {f["email"]: f["accion"] for f in j["filas"]} == {"marta@correo.com": "crear", "pedro@correo.com": "crear", "ana@conjunto.com": "actualizar"}
    assert db.query(Usuario).count() == antes


def test_aplicar_crea_cuentas_con_clave_temporal_y_actualiza_las_existentes(client, auth, db):
    r = subir(client, auth, "residentes", xlsx(CENSO), accion="aplicar")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["aplicado"] and j["crear"] == 2 and j["actualizar"] == 1 and len(j["credenciales"]) == 2
    marta = next(c for c in j["credenciales"] if c["email"] == "marta@correo.com")
    u = db.query(Usuario).filter(Usuario.email == "marta@correo.com").one()
    db.refresh(u)
    assert u.rol == "Residente" and u.apartamento == "Torre 3 Apt 301" and u.parqueadero_asignado == "P-7" and u.valor_administracion == 180000
    assert u.debe_cambiar_password is True and marta["clave_temporal"] not in u.password_encriptada      # en la BD no queda en claro
    # la clave temporal sirve para entrar, y el correo se guardó en minúscula
    assert client.post("/auth/login", data={"username": "marta@correo.com", "password": marta["clave_temporal"]}).status_code == 200
    assert db.query(Usuario).filter(Usuario.email == "pedro@correo.com").count() == 1
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    db.refresh(ana)
    assert ana.parqueadero_asignado == "P-1" and ana.valor_administracion == 200000
    assert client.post("/auth/login", data={"username": "ana@conjunto.com", "password": CLAVE}).status_code == 200   # su clave NO cambió
    assert db.query(Auditoria).filter(Auditoria.accion == "Importó el censo de residentes").count() == 1


def test_el_censo_rechaza_filas_malas_y_no_pisa_a_guardias_ni_administradores(client, auth, db):
    filas = [CENSO[0], ["Ok Bien", "ok@correo.com", "Torre 5 Apt 1", None, None],
             ["X", "corto@correo.com", "Apt 1", None, None],                       # nombre muy corto
             ["Sin Arroba", "sinarroba", "Apt 2", None, None],                      # correo inválido
             ["Sin Apto", "sinapto@correo.com", "", None, None],                    # apartamento vacío
             ["Cuota Mala", "cuota@correo.com", "Apt 3", None, "mucho"],            # cuota no numérica
             ["Repetido Uno", "rep@correo.com", "Apt 4", None, None], ["Repetido Dos", "REP@correo.com", "Apt 5", None, None],
             ["Quiere ser Guardia", "celador@conjunto.com", "Apt 6", None, None]]   # correo de un guardia
    j = subir(client, auth, "residentes", xlsx(filas)).json()
    assert (j["crear"], j["errores"]) == (2, 6)           # «Ok Bien» y «Repetido Uno»
    err = {f["fila"]: f["mensaje"] for f in j["filas"] if f["accion"] == "error"}
    assert "3 y 100" in err[3] and "no es válido" in err[4] and "obligatorio" in err[5] and "Cuota" in err[6]
    assert "ya aparece en la fila 7" in err[8] and "rol Guardia" in err[9]


def test_aplicar_con_errores_se_rechaza_salvo_que_se_pida_omitirlos(client, auth, db):
    filas = [CENSO[0], ["Ok Bien", "ok@correo.com", "Torre 5 Apt 1", None, None], ["X", "malo@correo.com", "Apt 1", None, None]]
    antes = db.query(Usuario).count()
    r = subir(client, auth, "residentes", xlsx(filas), accion="aplicar")
    assert r.status_code == 400 and "1 fila" in r.json()["detail"] and db.query(Usuario).count() == antes      # todo o nada
    r = subir(client, auth, "residentes", xlsx(filas), accion="aplicar", omitir_errores="true")
    assert r.status_code == 200 and r.json()["crear"] == 1 and db.query(Usuario).count() == antes + 1


def test_importar_dos_veces_el_mismo_censo_no_duplica_ni_cambia_claves(client, auth, db):
    subir(client, auth, "residentes", xlsx(CENSO), accion="aplicar")
    j = subir(client, auth, "residentes", xlsx(CENSO), accion="aplicar").json()
    assert j["crear"] == 0 and j["credenciales"] == [] and j["sin_cambios"] == 3
    assert db.query(Usuario).filter(Usuario.email == "marta@correo.com").count() == 1


# ---------------------------------------------------------------- formatos de archivo
def test_csv_con_punto_y_coma_tildes_en_windows_y_columnas_de_otro_software(client, auth, db):
    contenido = "Reporte de cartera - Siigo\r\nGenerado 14/11/2026\r\n\r\nApto;Saldo\r\nTorre 1 Apt 101;$ 1.250.000\r\nTorre 2 Apt 202;0\r\n".encode("cp1252")
    r = client.post("/importaciones/cartera/vista-previa", files={"archivo": ("siigo.csv", contenido, "text/csv")}, headers=auth("admin@conjunto.com"))
    assert r.status_code == 200, r.text
    assert [(f["apartamento"], f["saldo_nuevo"], f["accion"]) for f in r.json()["filas"]] == [("Torre 1 Apt 101", 1250000, "actualizar"), ("Torre 2 Apt 202", 0, "sin_cambios")]


def test_encabezados_con_tildes_mayusculas_y_nombres_alternativos(client, auth):
    datos = xlsx([["Nombre", "Correo electrónico", "Inmueble"], ["Lucía Vega", "lucia@correo.com", "Torre 9 Apt 9"]])
    j = subir(client, auth, "residentes", datos).json()
    assert j["crear"] == 1 and j["filas"][0]["nombre"] == "Lucía Vega"


@pytest.mark.parametrize("nombre,datos,codigo,texto", [
    ("a.xls", b"x", 400, ".xls"), ("a.pdf", b"x", 400, "Excel"), ("vacio.csv", b"", 400, "vacío"),
    ("roto.xlsx", b"esto no es un excel", 400, "Excel"), ("pk.xlsx", b"PK\x03\x04basura", 400, "No se pudo leer"),
    ("solo_titulos.csv", "foo;bar\n1;2\n".encode(), 400, "encabezados"), ("sin_filas.csv", "nombre;correo;apto\n".encode(), 400, "no tiene filas"),
    ("grande.csv", b"a" * (2 * 1024 * 1024 + 10), 413, "MB")])
def test_archivos_invalidos_dan_un_mensaje_claro(client, auth, nombre, datos, codigo, texto):
    r = client.post("/importaciones/residentes/vista-previa", files={"archivo": (nombre, datos, "application/octet-stream")}, headers=auth("admin@conjunto.com"))
    assert r.status_code == codigo and texto in r.json()["detail"]


def test_mas_de_1000_filas_se_rechaza(client, auth):
    filas = [CENSO[0]] + [[f"Persona {i}", f"p{i}@correo.com", f"Apt {i}", None, None] for i in range(1001)]
    r = subir(client, auth, "residentes", xlsx(filas))
    assert r.status_code == 400 and "1000" in r.json()["detail"]


def test_mil_filas_exactas_funcionan_y_la_vista_previa_no_se_infla(client, auth):
    filas = [CENSO[0]] + [[f"Persona {i}", f"p{i}@correo.com", f"Apt {i}", None, None] for i in range(1000)]
    j = subir(client, auth, "residentes", xlsx(filas)).json()
    assert j["crear"] == 1000 and len(j["filas"]) == 400 and j["filas_omitidas"] == 600


# ---------------------------------------------------------------- cartera
def _cartera_base(db):
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    ana.saldo_pendiente, ana.esta_al_dia = 0, True
    luis = db.query(Usuario).filter(Usuario.email == "luis@conjunto.com").one()
    luis.saldo_pendiente, luis.esta_al_dia = 300000, False
    db.commit()


def test_cartera_por_correo_y_por_apartamento_actualiza_la_mora(client, auth, db):
    _cartera_base(db)
    filas = [["email", "apartamento", "saldo_pendiente"], ["ana@conjunto.com", None, "$ 450.000"], [None, "torre 2  apt 202", 0]]   # luis (por apartamento, sin importar mayúsculas) paga todo
    j = subir(client, auth, "cartera", xlsx(filas), accion="aplicar").json()
    assert j["actualizar"] == 2 and j["entraron_en_mora"] == 1 and j["salieron_de_mora"] == 1
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one(); luis = db.query(Usuario).filter(Usuario.email == "luis@conjunto.com").one()
    db.refresh(ana); db.refresh(luis)
    assert (ana.saldo_pendiente, ana.esta_al_dia) == (450000, False) and (luis.saldo_pendiente, luis.esta_al_dia) == (0, True)
    # y la mora real bloquea reservas (la regla de siempre)
    r = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": "2030-01-10T10:00:00"}, headers=auth("ana@conjunto.com"))
    assert r.status_code == 403
    assert db.query(Auditoria).filter(Auditoria.accion == "Importó la cartera").count() == 1


def test_cartera_vista_previa_no_modifica_y_marca_lo_que_no_cambia(client, auth, db):
    _cartera_base(db)
    filas = [["email", "saldo_pendiente"], ["ana@conjunto.com", 0], ["luis@conjunto.com", 100000]]
    j = subir(client, auth, "cartera", xlsx(filas)).json()
    assert {f["email"]: f["accion"] for f in j["filas"]} == {"ana@conjunto.com": "sin_cambios", "luis@conjunto.com": "actualizar"}
    luis = db.query(Usuario).filter(Usuario.email == "luis@conjunto.com").one(); db.refresh(luis)
    assert luis.saldo_pendiente == 300000


def test_cartera_errores_apartamento_desconocido_repetido_ambiguo_o_de_un_guardia(client, auth, db):
    _cartera_base(db)
    otro = db.query(Usuario).filter(Usuario.email == "luis@conjunto.com").one()
    db.add(Usuario(nombre_completo="Vecino Mismo Apto", email="vecino@x.com", password_encriptada="x", rol_id=otro.rol_id, apartamento="Torre 2 Apt 202"))
    db.commit()
    filas = [["email", "apartamento", "saldo_pendiente"],
             [None, "Torre 99 Apt 1", 1000],                    # no existe
             [None, "Torre 2 Apt 202", 1000],                   # dos residentes en el mismo apartamento
             ["ana@conjunto.com", None, 1000], ["ana@conjunto.com", None, 2000],     # repetido
             ["celador@conjunto.com", None, 1000],              # no es residente
             [None, None, 1000], ["ana@conjunto.com", None, "mucho"], ["ana2@conjunto.com", None, -5]]
    j = subir(client, auth, "cartera", xlsx(filas)).json()
    err = {f["fila"]: f["mensaje"] for f in j["filas"] if f["accion"] == "error"}
    assert j["actualizar"] == 1 and j["errores"] == 7
    assert "No encontré" in err[2] and "2 residentes" in err[3] and "fila 4" in err[5] and "No encontré" in err[6]
    assert "Falta el correo" in err[7] and "Saldo" in err[8] and "negativo" in err[9]


def test_cartera_acepta_el_saldo_como_numero_de_excel(client, auth, db):
    _cartera_base(db)
    j = subir(client, auth, "cartera", xlsx([["Correo", "Deuda"], ["luis@conjunto.com", 123456.0]]), accion="aplicar").json()
    assert j["actualizar"] == 1
    luis = db.query(Usuario).filter(Usuario.email == "luis@conjunto.com").one(); db.refresh(luis)
    assert luis.saldo_pendiente == 123456
