# Paso 39 — Precios y costes con la factura real

## 1. Objetivo

Octavo paso del [plan de la versión 4.0.0](plan-version-4.md) (B-098): contrastar la estimación
de la telemetría con la factura real de Azure de los días con llamadas reales (24 al 27/10/2026),
incluido el caso del manual (Paso 36), como en el
[mantenimiento de octubre](mantenimiento-2026-10-factura.md), y ajustar precios, estimaciones y
costes orientativos.

Fuente: análisis de costes del recurso de Azure AI Services exportado por el usuario (medidor por
día, en EUR). No se versiona: contiene el ID de la suscripción y el nombre del recurso. Se
compara con todas las llamadas reales registradas esos días (138, sin duplicados, en `data/` y
en las copias locales de pruebas).

## 2. Resultados

| Despliegue | Estimado | Facturado | Observación |
|------------|---------:|----------:|-------------|
| `gpt-image-2.5-flare` (bocetos) | 1,7568 € | 1,7620 € | Igual desde el 25/10 |
| `gpt-image-2.5-sunburst` (composición) | 0,9426 € | 0,9549 € | Igual desde el 25/10 |
| `gpt-6-astra` (auditoría) | 0,6462 € | 0,6528 € | Igual desde el 25/10 |
| `gpt-6-luna` (prompts) | 0,1204 € | 0,1204 € | Igual |
| `gpt-6.1-sol` (recetas) | 0,8474 € | 0,0000 € | Sigue a 0 €, como en octubre |
| `FLUX.2-pro` (render final) | 1,6584 € | 1,9941 € | Referencias por MP real (abajo) |
| **Total** | **5,9718 €** | **5,4842 €** | |

- **Desde el 25/10 todo cuadra:** con las referencias de FLUX por MP real, los timeouts a 0 € y
  `gpt-6.1-sol` a 0 €, la estimación habría sido 5,1618 € frente a 5,1623 € facturados.
- **El factor 0,98463 se mantiene** en todos los medidores (mismos tokens y megapíxeles que la
  telemetría; el euro, algo más barato que la lista).
- **24/10:** unos 0,12 € facturados sin registro en la telemetría (unos 3 renders de FLUX y
  alguna llamada de auditoría y de bocetos). Casi seguro, pruebas del Paso 24 («5 renders») en
  proyectos o copias que ya no existen.
- **Caso del manual:** estimado 1,57 €; facturado ≈ 1,40 € (las recetas salieron a 0 € y FLUX
  algo más caro). El 27/10 incluye además 5 llamadas posteriores del usuario (0,23 €).

### FLUX.2-pro

| Medidor | Estimación anterior | Factura |
|---------|---------------------|---------|
| Primer MP de cada imagen | 1 por imagen | Igual |
| MP adicionales | MP binario | Igual |
| Referencias | 1 MP por imagen (`per_image`, octubre) | **MP binario del tamaño real de cada una**: 1,5 MP por una composición de 1536×1024 y 2,67 MP por un render reducido a 2048×1365. Cuadra en las 21 llamadas del 25 al 27/10 |
| Timeout | Se le asignaban sus referencias (0,013 €) | **No se cobra** (igual que los de la auditoría en octubre) |

En octubre cada render enviaba varias referencias y no salió así; ahora solo se envía la imagen
de partida.

## 3. Decisiones (usuario, 2026-10-29)

| Tema | Decisión |
|------|----------|
| Referencias de FLUX | Por los MP de su tamaño real (`reference_mode: pixels`); la estimación junto a los botones usa la imagen de partida |
| Llamadas con error | A 0 €, salvo los tokens que el proveedor informe: una respuesta incompleta sí se cobra (lo mostró un test: así se había medido) |
| `gpt-6.1-sol` | Mantiene su precio de lista, sin explicarlo en el README ni en la web |
| Factor de facturación | **Fuera** (`billing_factor` vuelve a 1.0): precios de lista tal cual, con todos sus decimales; mejor ver en Azure menos gasto del previsto que al revés |
| Redondeo | **Al céntimo hacia arriba** en las estimaciones y los resúmenes: pistas junto a los botones, confirmaciones (el umbral de 0,20 € se compara con ese importe), indicadores, coste de la cadena, gráficos, avisos, cabecera, resumen del proyecto, README y web. El importe guardado sigue exacto (las sumas se hacen antes de redondear); el registro de llamadas, su detalle, el CSV y la API, con 4 decimales |
| Costes orientativos | Los medidos en el caso del manual, al céntimo hacia arriba |

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| `config/pricing.yaml` | Sin `billing_factor` ni `reference_mode: per_image` (los dos, a su valor por defecto); comentarios con lo observado |
| `backend/app/telemetry/metered.py` | Con error, no se cobran las imágenes de referencia; los tokens informados por el proveedor, sí |
| `frontend/ui/money.py` (nuevo) | `cents_up` y `euros_up`: al céntimo hacia arriba sin errores de coma flotante |
| Estimaciones (`studio_views.py`, `tabs/studio.py`) | Pistas, confirmación y textos tras cada acción al céntimo hacia arriba; render final con los MP de la imagen de partida (`final_source`, `source_megapixels`: composición seleccionada, render final seleccionado o la partida del original en «Otra versión»); auditoría estimada en 0,30 € (antes 0,25 €, por debajo de la mayor medida, 0,27 €); retoque, 0,07 € |
| Resúmenes (`cost_views.py`, `views.py`, `tabs/references.py`) | Indicadores, coste de la cadena, avisos, gráficos (la ayuda emergente), cabecera, resumen del proyecto y aviso de la receta, al céntimo hacia arriba; el registro y su detalle, exactos. Aviso de Costes IA con la regla de los errores |
| Documentación | README y web (costes orientativos, referencia de IA y costes, manual: lo que costó, Costes IA y Render final), `docs/agent/azure_foundry.md` |

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 366. Nuevos o rehechos: la tabla de precios queda un 1,5 % por encima de las facturas (auditoría y bocetos del 18/10, FLUX del 26/10), un timeout no cuesta aunque lleve referencias, redondeo y umbral de confirmación, estimación del render final según su partida |
| Navegador (aplicación local en modo simulación con un proxy que anuncia Azure; ningún botón con coste pulsado) | ✅ Bocetos 0,25 €; composición 0,08 €; auditoría 0,30 €; render final 0,09 € desde la composición y 0,11 € desde el render; «Otra versión» 0,10 €; cadena 0,66 €; indicador 1,80 €; resumen del proyecto y aviso de la receta redondeados; aviso nuevo de los errores |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |

Coste real del paso: 0 €. Las estimaciones ya registradas no se recalculan.

## 6. Estado final

⏳ En revisión — rama `feat/paso-39`.

## 7. Pendiente / futuro

- Paso 40: versión 4.0.0 (etiqueta y Release con el OK del usuario).
- Volver a contrastar si cambia mucho el tipo de cambio o si `gpt-6.1-sol` empieza a cobrarse.
