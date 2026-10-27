# Plan de acción — InteriorAI 4.0.0

Propuesto el 2026-10-27, tras publicar la 3.0.0. Reúne los prompts más precisos del Paso 32
(B-054, B-094 a B-097, ya hechos), la retirada de la compatibilidad con la v1 (B-056) y la
actualización de precios y costes con la factura real de Azure (B-098).

## Por qué 4.0.0

Retirar la v1 quita endpoints (`/briefs`) y campos de la API y del modelo de datos (esquema v3,
con migración automática). Según SemVer, un cambio incompatible es una versión mayor, como en la
2.0.0 y la 3.0.0 (decisión del usuario, 2026-10-27). Los datos de la 1.0.0 dejan de leerse:
quien venga de ella actualiza antes a la 3.0.0.

## Pasos

| Paso | Contenido | Entradas | Llamadas reales |
|------|-----------|----------|-----------------|
| 32. Prompts del PROMPT_ARCHITECT ✅ | Criterios comunes, más contexto, imágenes con detalle alto, tope de salida y timeout propio | B-054, B-094 a B-097 | 0,38 € (hecho) |
| 33. Retirar la compatibilidad con la v1 ⏳ | Esquema v3 con migración automática (copia en `metadatos.v2.json`, también al restaurar de la papelera): las imágenes de la v1 quedan como imágenes sueltas, sin su cadena; las referencias con tipo antiguo, como referencias normales. Fuera los briefs (endpoints, pipeline, prompt y estados), las cadenas de la v1 en composición y render final, la auditoría frente a la captura, el puente `legacy_kind`, la migración desde la 1.0.0, el coste de cadena de la v1 y los textos de la v1 en la interfaz, Postman y tests | B-056 | No |
| 34. Precios y costes reales | Contraste de la estimación con la factura real de Azure de los últimos días (como el mantenimiento de octubre): `config/pricing.yaml`, factor de facturación y costes orientativos del README. El usuario aporta los datos de Azure Cost Management | B-098 | No |
| 35. Versión 4.0.0 | README, CHANGELOG (nota de actualización: datos de la 1.0.0 vía la 3.0.0), versión en los `pyproject.toml`, etiqueta y Release con el OK del usuario | — | No |

## Decisiones tomadas (usuario, 2026-10-27)

1. **Imágenes de la v1 de los datos reales** (los dos proyectos de prueba): se conservan como
   imágenes sueltas, sin la cadena de la v1 (brief, rechazos, salidas en bruto de los retoques).
2. **Datos de la 1.0.0** (esquema 1): dejan de leerse; se quita la migración v1 → v2.
3. **Versión 4.0.0**, con los prompts del Paso 32 y la actualización de precios.

## Lo que aporta el usuario

- Paso 34: los costes reales de Azure de los últimos días (Cost Management).
