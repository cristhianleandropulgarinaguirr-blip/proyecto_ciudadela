# app/importacion.py
# Lectura y validación de las planillas que sube el administrador (Excel .xlsx o CSV) para cargar de golpe:
#   · «residentes» → el censo de apartamentos (crea las cuentas que falten y actualiza las existentes).
#   · «cartera»    → el saldo de cada apartamento, tal como sale del software contable (Siigo, World Office, Alegra…).
# Este módulo NO toca la base de datos ni FastAPI: solo convierte el archivo en filas ya validadas. Así se prueba solo y es
# la misma lógica para la «vista previa» (que no guarda nada) y para «aplicar».
import csv
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from pydantic import EmailStr, TypeAdapter, ValidationError

MAX_BYTES = 2 * 1024 * 1024          # una planilla de 1.000 filas pesa ~60 KB; 2 MB sobra y frena archivos disfrazados
MAX_FILAS = 1000
FILAS_BUSQUEDA_ENCABEZADO = 20       # los exportes contables traen títulos antes de la tabla: se busca el encabezado en las primeras filas

# Nombres que se aceptan para cada columna (ya sin tildes, en minúscula y con «_»). Así sirve la plantilla nuestra y los exportes de Siigo/World Office/Alegra.
ALIAS: dict[str, dict[str, set[str]]] = {
    "residentes": {
        "nombre_completo": {"nombre_completo", "nombre", "nombres", "nombre_y_apellido", "nombre_y_apellidos", "residente", "propietario", "titular"},
        "email": {"email", "correo", "correo_electronico", "e_mail", "mail"},
        "apartamento": {"apartamento", "apto", "apt", "inmueble", "unidad", "casa"},
        "parqueadero": {"parqueadero", "parqueo", "garaje", "garage"},
        "valor_administracion": {"valor_administracion", "cuota", "cuota_administracion", "cuota_mensual", "valor_cuota", "administracion"},
        "coeficiente": {"coeficiente", "coeficiente_copropiedad", "coeficiente_de_copropiedad", "coef", "indiviso", "porcentaje_copropiedad", "participacion"},
    },
    "cartera": {
        "email": {"email", "correo", "correo_electronico", "e_mail", "mail"},
        "apartamento": {"apartamento", "apto", "apt", "inmueble", "unidad", "casa"},
        "saldo_pendiente": {"saldo_pendiente", "saldo", "deuda", "cartera", "valor", "total", "saldo_a_pagar", "valor_pendiente", "saldo_total", "total_deuda"},
    },
}
# Columnas sin las cuales la planilla no sirve (de «cartera» basta con una de email/apartamento, se valida aparte).
OBLIGATORIAS = {"residentes": {"nombre_completo", "email", "apartamento"}, "cartera": {"saldo_pendiente"}}
TITULOS = {"nombre_completo": "nombre_completo", "email": "email", "apartamento": "apartamento", "parqueadero": "parqueadero",
           "valor_administracion": "valor_administracion", "saldo_pendiente": "saldo_pendiente", "coeficiente": "coeficiente"}

_EMAIL = TypeAdapter(EmailStr)


class ErrorDeArchivo(ValueError):
    """Problema con el archivo en sí (formato, tamaño, encabezados): se le explica al administrador y no se procesa nada."""


def normalizar_encabezado(texto: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def clave_apartamento(texto: Any) -> str:
    """Para comparar apartamentos sin que importen mayúsculas, tildes ni espacios de más: «Torre 1  Apt 101» = «torre 1 apt 101»."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _celda(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))                     # Excel guarda el 101 como 101.0
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return " ".join(str(v).split())            # sin saltos de línea ni espacios dobles


def parsear_coeficiente(valor: Any) -> float:
    """«0,8523», «0.8523», «0,8523 %» → 0.8523 (porcentaje). Acepta coma o punto decimal. Debe estar entre 0 (sin incluir) y 100."""
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        t = re.sub(r"[\s%]", "", str(valor or "")).replace(",", ".")
        if not t:
            raise ValueError("está vacío")
        if t.count(".") > 1:
            raise ValueError(f"«{valor}» no es un número (usa una sola coma o punto decimal)")
        try:
            n = float(t)
        except ValueError:
            raise ValueError(f"«{valor}» no es un número")
    if not 0 < n <= 100:
        raise ValueError("debe ser un porcentaje mayor que 0 y de máximo 100 (por ejemplo 0,8523)")
    return round(n, 4)


def parsear_dinero(valor: Any) -> int:
    """«$ 1.250.000», «1,250,000», «1250000.00», 1250000.0 → 1250000. Entiende el formato colombiano (punto de miles, coma decimal)."""
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        t = re.sub(r"[\s$]|COP", "", str(valor or ""), flags=re.I)
        if not t:
            raise ValueError("el saldo está vacío")
        negativo = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
        t = t.strip("()-")
        if not re.fullmatch(r"[0-9.,]+", t):
            raise ValueError(f"«{valor}» no es un valor numérico")
        if "." in t and "," in t:                                   # el último separador es el decimal
            dec = "," if t.rfind(",") > t.rfind(".") else "."
            t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
        elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):                # un solo tipo de separador, en grupos de 3: son miles
            t = re.sub(r"[.,]", "", t)
        else:
            t = t.replace(",", ".")
        if t.count(".") > 1:
            raise ValueError(f"«{valor}» no es un valor numérico")
        n = -float(t) if negativo else float(t)
    if n < 0:
        raise ValueError("el saldo no puede ser negativo")
    if n > 2_000_000_000:
        raise ValueError("el valor es demasiado grande")
    return int(round(n))


# ---------------------------------------------------------------- lectura del archivo
def _filas_xlsx(datos: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook
    if not datos.startswith(b"PK"):
        raise ErrorDeArchivo("El archivo no es un Excel .xlsx válido. Si es un .xls antiguo, ábrelo y guárdalo como .xlsx o como CSV.")
    try:
        libro = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
        hoja = libro.worksheets[0]
        filas = [list(f) for f in hoja.iter_rows(values_only=True, max_row=MAX_FILAS + FILAS_BUSQUEDA_ENCABEZADO + 1)]
        libro.close()
        return filas
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, IndexError) as e:
        raise ErrorDeArchivo("No se pudo leer el Excel: parece dañado o no es un .xlsx.") from e


def _filas_csv(datos: bytes) -> list[list[Any]]:
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252", errors="replace")      # el CSV que guarda Excel en Windows
    muestra = texto[:4096]
    try:
        sep = csv.Sniffer().sniff(muestra, delimiters=",;\t").delimiter
    except csv.Error:
        sep = ";" if muestra.count(";") > muestra.count(",") else ","
    return [list(f) for f in csv.reader(io.StringIO(texto), delimiter=sep)][: MAX_FILAS + FILAS_BUSQUEDA_ENCABEZADO + 1]


def leer_tabla(nombre_archivo: str, datos: bytes, tipo: str) -> tuple[list[dict[str, str]], list[int]]:
    """Devuelve (filas, numeros_de_fila). Cada fila es {columna_oficial: texto}. El número de fila es el que ve el administrador en su Excel."""
    if tipo not in ALIAS:
        raise ErrorDeArchivo("Tipo de planilla desconocido.")
    if not datos:
        raise ErrorDeArchivo("El archivo está vacío.")
    if len(datos) > MAX_BYTES:
        raise ErrorDeArchivo(f"El archivo pesa más de {MAX_BYTES // 1024 // 1024} MB. Divídelo en partes.")
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".xlsx") or nombre.endswith(".xlsm"):
        crudas = _filas_xlsx(datos)
    elif nombre.endswith(".csv") or nombre.endswith(".txt"):
        crudas = _filas_csv(datos)
    elif nombre.endswith(".xls"):
        raise ErrorDeArchivo("El formato .xls antiguo no se admite. Ábrelo en Excel y guárdalo como .xlsx (o como CSV).")
    else:
        raise ErrorDeArchivo("Sube un archivo Excel (.xlsx) o CSV (.csv).")

    # Se busca la fila de encabezados: la primera donde se reconozca la columna obligatoria (o email/apartamento en cartera).
    reconocidas = ALIAS[tipo]
    obligatorias = OBLIGATORIAS[tipo]
    inicio, mapa = None, {}
    for i, fila in enumerate(crudas[:FILAS_BUSQUEDA_ENCABEZADO]):
        candidato = {}
        for j, celda in enumerate(fila):
            h = normalizar_encabezado(celda)
            for oficial, nombres in reconocidas.items():
                if h in nombres and oficial not in candidato:
                    candidato[oficial] = j
        if obligatorias <= candidato.keys() and (tipo != "cartera" or {"email", "apartamento"} & candidato.keys()):
            inicio, mapa = i, candidato
            break
    if inicio is None:
        faltan = ", ".join(sorted(obligatorias)) + (" y «email» o «apartamento»" if tipo == "cartera" else "")
        raise ErrorDeArchivo(f"No encontré los encabezados. La planilla debe tener las columnas: {faltan}. Descarga la plantilla para ver el formato.")

    filas, numeros = [], []
    for i, fila in enumerate(crudas[inicio + 1:], start=inicio + 2):
        valores = {oficial: _celda(fila[j]) if j < len(fila) else "" for oficial, j in mapa.items()}
        if not any(valores.values()):
            continue                                                    # filas en blanco (muy comunes al final de un Excel)
        filas.append(valores)
        numeros.append(i)
    if len(filas) > MAX_FILAS:
        raise ErrorDeArchivo(f"La planilla tiene más de {MAX_FILAS} filas. Divídela en partes para importarla.")
    if not filas:
        raise ErrorDeArchivo("La planilla no tiene filas de datos debajo de los encabezados.")
    return filas, numeros


# ---------------------------------------------------------------- validación de cada fila
@dataclass
class Fila:
    numero: int
    accion: str = "error"                     # crear | actualizar | sin_cambios | error
    mensaje: str = ""
    datos: dict = field(default_factory=dict)  # valores ya limpios
    usuario_id: Optional[int] = None           # a quién se aplica (actualizar / cartera)


def validar_residente(numero: int, v: dict[str, str]) -> Fila:
    f = Fila(numero)
    nombre = v.get("nombre_completo", "")
    if len(nombre) < 3 or len(nombre) > 100:
        f.mensaje = "El nombre debe tener entre 3 y 100 caracteres."
        return f
    try:
        email = str(_EMAIL.validate_python(v.get("email", "").lower()))
    except ValidationError:
        f.mensaje = f"El correo «{v.get('email', '')}» no es válido."
        return f
    apto = v.get("apartamento", "")
    if not apto or len(apto) > 50:
        f.mensaje = "El apartamento es obligatorio (máximo 50 caracteres)."
        return f
    datos = {"nombre_completo": nombre, "email": email.lower(), "apartamento": apto}
    if v.get("parqueadero"):
        if len(v["parqueadero"]) > 30:
            f.mensaje = "El parqueadero es demasiado largo (máximo 30 caracteres)."
            return f
        datos["parqueadero_asignado"] = v["parqueadero"]
    if v.get("valor_administracion"):
        try:
            datos["valor_administracion"] = parsear_dinero(v["valor_administracion"])
        except ValueError as e:
            f.mensaje = f"Cuota de administración: {e}."
            return f
    if v.get("coeficiente"):
        try:
            datos["coeficiente"] = parsear_coeficiente(v["coeficiente"])
        except ValueError as e:
            f.mensaje = f"Coeficiente: {e}."
            return f
    f.datos, f.accion = datos, "crear"           # el servicio decide si es «crear» o «actualizar» según exista el correo
    return f


def validar_cartera(numero: int, v: dict[str, str]) -> Fila:
    f = Fila(numero)
    try:
        saldo = parsear_dinero(v.get("saldo_pendiente", ""))
    except ValueError as e:
        f.mensaje = f"Saldo: {e}."
        return f
    email, apto = v.get("email", "").lower(), v.get("apartamento", "")
    if not email and not apto:
        f.mensaje = "Falta el correo o el apartamento para saber a quién corresponde el saldo."
        return f
    if email:
        try:
            email = str(_EMAIL.validate_python(email)).lower()
        except ValidationError:
            f.mensaje = f"El correo «{email}» no es válido."
            return f
    f.datos, f.accion = {"email": email, "apartamento": apto, "saldo_pendiente": saldo}, "actualizar"
    return f
