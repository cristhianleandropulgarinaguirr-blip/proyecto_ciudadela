// Prueba: todo `import { algo } from "./archivo.js"` del frontend debe existir de verdad.
// Evita errores como «The requested module './ui.js' does not provide an export named 'diaLocal'»: ese fallo solo aparece
// cuando alguien abre la pantalla que lo usa, y esta prueba lo detecta antes de subir los cambios.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../frontend");
const recorrer = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? (e.name === "vendor" ? [] : recorrer(path.join(d, e.name))) : [path.join(d, e.name)]);
const archivos = recorrer(RAIZ).filter((f) => f.endsWith(".js"));

const exportes = (src) => {
  const s = new Set();
  for (const m of src.matchAll(/export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z0-9_$]+)/g)) s.add(m[1]);
  for (const m of src.matchAll(/export\s*\{([^}]*)\}/g)) for (const p of m[1].split(",")) { const n = p.trim().split(/\s+as\s+/).pop().trim(); if (n) s.add(n); }
  if (/export\s+default/.test(src)) s.add("default");
  return s;
};
const tabla = new Map(archivos.map((f) => [path.resolve(f), exportes(fs.readFileSync(f, "utf8"))]));

test("todos los imports del frontend apuntan a archivos y exportaciones que existen", () => {
  const problemas = [];
  for (const f of archivos) {
    const limpio = fs.readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
    const revisar = (especificador, nombres) => {
      if (!especificador.startsWith(".")) return;
      const destino = path.resolve(path.dirname(f), especificador);
      if (!tabla.has(destino)) return problemas.push(`${path.relative(RAIZ, f)}: «${especificador}» no existe`);
      for (const n of nombres) if (!tabla.get(destino).has(n)) problemas.push(`${path.relative(RAIZ, f)}: «${n}» no se exporta desde ${especificador}`);
    };
    for (const m of limpio.matchAll(/import\s*\{([^}]*)\}\s*from\s*["']([^"']+)["']/g)) revisar(m[2], m[1].split(",").map((p) => p.trim().split(/\s+as\s+/)[0].trim()).filter(Boolean));
    for (const m of limpio.matchAll(/(?:const|let)\s*\{([^}]*)\}\s*=\s*await\s+import\(\s*["']([^"']+)["']\s*\)/g)) revisar(m[2], m[1].split(",").map((p) => p.trim().split(":")[0].trim()).filter(Boolean));
    for (const m of limpio.matchAll(/import\(\s*["']([^"']+)["']\s*\)/g)) revisar(m[1], []);
    for (const m of limpio.matchAll(/import\s*["']([^"']+)["']/g)) revisar(m[1], []);
  }
  assert.deepEqual(problemas, [], "Imports rotos:\n" + problemas.join("\n"));
});
