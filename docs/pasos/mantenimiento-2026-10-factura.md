# Mantenimiento — Contraste con la factura real de Azure (octubre de 2026)

## 1. Objetivo

Comparar el coste **estimado** por la telemetría con el **facturado** por Azure Cost Management
(B-011), averiguar cuánto costó el timeout de la primera auditoría (B-016) y ajustar la
estimación a lo observado.

Fuente: análisis de costes de octubre del recurso de Azure AI Services, exportado por el usuario
(medidor por día, en EUR). El archivo no se versiona: contiene el ID de la suscripción y el nombre
del recurso, y el repositorio es público.

## 2. Resultados

**18/10/2026** (único día con llamadas reales de InteriorAI; 28 llamadas en dos proyectos):

| Despliegue | Estimado | Facturado | Observación |
|------------|---------:|----------:|-------------|
| `FLUX.2-pro` (13 renders) | 1,0251 € | 0,9133 € | MP binario y 1 MP por referencia (ver abajo) |
| `gpt-6-astra` (auditoría) | 0,2946 € | 0,2900 € | Lista × 0,98463; el timeout no se facturó |
| `gpt-image-2.5-sunburst` | 0,1572 € | 0,1548 € | Lista × 0,98463 |
| `gpt-image-2.5-flare` | 0,1112 € | 0,1095 € | Lista × 0,98463 |
| `gpt-6.1-sol` (brief) | 0,0558 € | **0,0000 €** | Todos sus medidores a 0 € del 14 al 22/10 |
| `gpt-6-luna` | 0,0008 € | 0,0008 € | Lista × 0,98463 |
| **Total** | **1,6447 €** | **1,4683 €** | −10,7 % |

Los costes del 1 y el 11 de octubre (1,07 €) son de otras pruebas en el mismo recurso, anteriores
a InteriorAI. Las 6 llamadas de verificación del Paso 6 (≈ 0,09 € estimados) no aparecen.

### Modelos de OpenAI: mismos tokens, precio en euros un 1,5 % menor

En los cuatro despliegues con coste, **cada medidor** (entrada, escritura en caché, salida,
tokens de texto y de imagen) sale exactamente a nuestro cálculo × **0,98463**: las cantidades de
tokens coinciden con la telemetría y solo cambia el precio en euros (tipo de cambio).

### B-016: el timeout de la auditoría costó 0 €

Lo facturado a `gpt-6-astra` corresponde a las dos auditorías que terminaron (escritura en
caché 11.673 tokens frente a 11.855; salida 3.673 frente a 3.730; ambas × 0,98463). Los cuatro
intentos cortados por timeout no se facturaron.

### FLUX.2-pro: cómo factura los megapíxeles

| Medidor | Antes | Facturado |
|---------|-------|-----------|
| Primer MP de cada imagen | 1 por imagen | Igual (13) |
| MP adicionales | MP decimal (10⁶ px): 15,63 | **MP binario (2²⁰ px)**: 14,27 (nuestro cálculo binario, 14,31) |
| Referencias | Píxeles de cada una: 36,03 | **≈ 1 MP por imagen**: 30,0 con 29 referencias enviadas |

El redondeo hacia arriba (`ceil`) queda descartado. La diferencia de 1 MP en las referencias no
se puede explicar sin la cantidad por llamada (el informe es diario).

## 3. Decisiones

| Decisión | Motivo |
|----------|--------|
| `billing_factor: 0.98463` en `config/pricing.yaml`, sin tocar los precios de lista | Precios trazables; el factor se revisa si cambia mucho el tipo de cambio |
| `megapixel_px: 1048576` (MP binario) | Lo que factura Azure en FLUX |
| `reference_mode: per_image` en FLUX (1 MP por referencia) | Lo observado en la factura |
| **`gpt-6.1-sol` mantiene su precio de lista** (decisión del usuario) | Evitar sorpresas si empieza a cobrarse: las estimaciones de los briefs quedan algo por encima de la factura |
| Cerrar **B-015** (reducir las imágenes de entrada) | En FLUX cada referencia cuesta lo mismo sea cual sea su tamaño; en el resto, céntimos |

Con estos cambios, la estimación del 18/10 sería 1,511 € (1,456 € sin el brief, que Azure no
cobró, frente a 1,468 € facturados).

## 4. Implementación y validación

| Archivo | Cambio |
|---------|--------|
| `backend/app/telemetry/pricing.py` | `billing_factor`, `megapixel_px`, `reference_mode` (por defecto, el comportamiento anterior) |
| `config/pricing.yaml` | Valores observados y comentarios |
| `backend/tests/test_telemetry_pricing.py` | Fórmulas con precios de lista; test nuevo que reproduce la factura (auditoría 0,290049 €, bocetos 0,109456 €, FLUX) |
| `backend/tests/test_telemetry_metered.py`, `test_api_audit.py`, `test_api_renders.py` | Importes con el factor |

`uv run pytest`: ✅ 339 passed. Las estimaciones ya registradas en la telemetría no se recalculan.

## 5. Estado final

✅ Cerrado — rama `fix/precios-facturados`, PR #21 revisada y mergeada por el usuario. Cierra
B-011, B-015 y B-016.
