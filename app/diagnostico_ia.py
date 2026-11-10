# app/diagnostico_ia.py — Diagnóstico del asistente de IA (versión 2.9).
# Uso (en la carpeta del proyecto, con el entorno virtual activado):   python -m app.diagnostico_ia
# Qué hace: lee tu .env, le pregunta a Google qué modelos tienes y prueba una consulta mínima, mostrando el motivo EXACTO del error.
# NUNCA imprime tu clave. Puedes copiar y pegar la salida completa para pedir ayuda.
import sys
from typing import Optional

import httpx

from app import config
from app.ia import MODELOS_POR_DEFECTO, URL_GEMINI, URL_GROQ

EXCLUIR = ("preview", "tts", "image", "live", "lite", "exp", "embedding", "audio", "robotics", "computer", "thinking", "customtools", "deep", "veo", "imagen")
PRUEBA = {"systemInstruction": {"parts": [{"text": "Responde solo con JSON."}]}, "contents": [{"role": "user", "parts": [{"text": 'Responde {"ok": true}'}]}],
          "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 50}}


def _motivo(res: httpx.Response) -> str:
    try:
        e = res.json().get("error", {})
        return f"{e.get('status', '')} — {e.get('message', res.text[:200])}"
    except ValueError:
        return res.text[:200]


def probar_gemini(cliente: httpx.Client, modelo: str, cabeceras: dict) -> tuple[int, str]:
    res = cliente.post(f"{URL_GEMINI}/models/{modelo}:generateContent", json=PRUEBA, headers=cabeceras)
    return res.status_code, ("funciona" if res.status_code == 200 else _motivo(res))


def diagnosticar(cliente: Optional[httpx.Client] = None, salida=print) -> int:
    cliente = cliente or httpx.Client(timeout=30)
    clave = config.IA_API_KEY
    salida(f"Proveedor configurado: {config.PROVEEDOR_IA}")
    salida(f"Modelo configurado:    {config.IA_MODELO or '(por defecto) ' + MODELOS_POR_DEFECTO.get(config.PROVEEDOR_IA, '?')}")
    if not clave:
        salida("PROBLEMA: no hay IA_API_KEY en el .env (o el servidor no se reinició).")
        return 1
    salida(f"Clave: {len(clave)} caracteres, empieza por «{clave[:3]}»" + ("  ← OJO: la clave tiene espacios o comillas" if clave != clave.strip(' "\'') or ' ' in clave else ""))

    if config.PROVEEDOR_IA != "gemini":
        base = URL_GROQ if config.PROVEEDOR_IA == "groq" else config.IA_URL_BASE
        res = cliente.get(f"{base}/models", headers={"Authorization": f"Bearer {clave}"})
        salida(f"Lista de modelos: HTTP {res.status_code} {'' if res.status_code == 200 else _motivo(res)}")
        return 0 if res.status_code == 200 else 1

    cab = {"x-goog-api-key": clave}
    res = cliente.get(f"{URL_GEMINI}/models", params={"pageSize": 200}, headers=cab)
    salida(f"\n1) Lista de modelos de tu cuenta: HTTP {res.status_code}")
    candidatos: list[str] = []
    if res.status_code == 200:
        modelos = [m for m in res.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        nombres = sorted(m["name"].removeprefix("models/") for m in modelos)
        salida("   Modelos que sirven para generar texto: " + (", ".join(nombres) or "(ninguno)"))
        candidatos = [n for n in nombres if "flash" in n and not any(x in n for x in EXCLUIR)]
    else:
        salida(f"   Motivo: {_motivo(res)}")

    salida("\n2) Prueba de una consulta mínima:")
    a_probar = [config.IA_MODELO or MODELOS_POR_DEFECTO["gemini"]] + [c for c in candidatos if c != (config.IA_MODELO or MODELOS_POR_DEFECTO["gemini"])][:4]
    funciona = None
    for modelo in a_probar:
        codigo, detalle = probar_gemini(cliente, modelo, cab)
        salida(f"   {modelo}: HTTP {codigo} — {detalle}")
        if codigo == 200 and funciona is None:
            funciona = modelo
    salida("")
    if funciona:
        salida(f"RESULTADO: tu clave funciona. Pon en el .env (y en Render → Environment):  IA_MODELO={funciona}")
        return 0
    salida("RESULTADO: ningún modelo respondió bien. Mira el motivo de arriba. Si habla de la clave, crea otra en AI Studio; si no se arregla, usa PROVEEDOR_IA=groq.")
    return 1


if __name__ == "__main__":
    sys.exit(diagnosticar())
