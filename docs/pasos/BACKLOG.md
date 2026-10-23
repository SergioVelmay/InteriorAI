# Backlog consolidado

Elementos diferidos o pendientes de verificación. Cada entrada enlaza al paso que la originó.

| ID | Descripción | Origen | Destino previsto | Estado |
|----|-------------|--------|------------------|--------|
| B-001 | Verificar que el despliegue del Auditor Geométrico acepta `reasoning_effort: max` | [Paso 0](paso-00-plan-y-decisiones.md) | Paso 6 | ✅ Resuelto en [Paso 6](paso-06-foundry.md): acepta `max`; en el Paso 10 el usuario lo fija en `medium` |
| B-002 | Ejecutar gitleaks sobre todo el historial en CI (GitHub Actions) | [Paso 1](paso-01-repo-seguro.md) | Paso 15 | ✅ Resuelto en [Paso 15a](paso-15a-ci-seguridad.md): trabajo `gitleaks` de la CI |
| B-003 | Verificar si la API del renderizador (`/providers/...`) requiere `api-version` | [Paso 2](paso-02-configuracion.md) | Paso 6 | ✅ Resuelto en [Paso 6](paso-06-foundry.md): `api-version=preview` |
| B-004 | Activar Dependabot en GitHub | [Paso 2](paso-02-configuracion.md) | Paso 15 | ✅ Resuelto en [Paso 15a](paso-15a-ci-seguridad.md): uv, GitHub Actions y Docker, semanal y agrupado |
| B-005 | En hosts Linux, `data-init` cambia el propietario de `./data` a uid 1000: hacer configurable el UID/GID (`APP_UID`) si el usuario del host no es 1000 | [Paso 3](paso-03-docker.md) | Paso 15 | ✅ Resuelto en [Paso 15b](paso-15b-version-1.md): `APP_UID`/`APP_GID` en `.env` |
| B-006 | Detectar assets duplicados por `sha256` al subir (avisar al usuario) | [Paso 4](paso-04-almacenamiento.md) | Paso 5 | ✅ Resuelto en [Paso 5](paso-05-api.md) (409 + `allow_duplicate`) |
| B-007 | Comando para listar/restaurar/vaciar `.papelera/` (siempre con confirmación) | [Paso 4](paso-04-almacenamiento.md) | Paso 15 | ✅ Resuelto en [Paso 15b](paso-15b-version-1.md): `python -m app.storage papelera` |
| B-008 | Actualizar Postman CLI (instalada 1.73.0, disponible 1.75.0) | [Paso 5](paso-05-api.md) | Cuando el usuario lo decida | ⏳ Abierto |
| B-009 | La máscara de GPT-image es orientativa: recomponer en local solo la zona enmascarada para inpainting exacto | [Paso 6](paso-06-foundry.md) | Paso 13b | ✅ Resuelto en [Paso 13b](paso-13b-retoques.md): recomposición local de la zona; se guarda también la salida en bruto |
| B-010 | Precios reales de los 6 despliegues para `config/pricing.yaml` (los aporta el usuario) | [Paso 6](paso-06-foundry.md) | Paso 7 | ✅ Resuelto en [Paso 7](paso-07-telemetria.md) |
| B-011 | Contrastar en Azure Cost Management el redondeo de megapíxeles del renderizador (`exact` vs `ceil`) y, en general, el coste estimado frente al real | [Paso 7](paso-07-telemetria.md) | Cuando haya facturación de las llamadas reales | ✅ Resuelto ([factura de octubre](mantenimiento-2026-10-factura.md)): mismos tokens, precio × 0,98463; FLUX con MP binario y 1 MP por referencia |
| B-012 | `costes_telemetria.json` se reescribe entero en cada registro: valorar rotación o JSONL si un proyecto acumula miles de llamadas | [Paso 7](paso-07-telemetria.md) | Paso 15 | ⏳ Abierto |
| B-013 | Enviar planos PDF al PROMPT_ENGINEER con `input_file` (Responses API) tras verificarlo en Azure | [Paso 8](paso-08-pipelines-texto.md) | Paso 9-10 | ✅ Cerrado en [Paso 12](paso-12-ui-assets.md): no aplica, los planos son imágenes |
| B-014 | Generar el brief tarda ~40 s: indicador de progreso o tarea en segundo plano en la UI | [Paso 8](paso-08-pipelines-texto.md) | Paso 13 | ✅ Resuelto en [Paso 13a](paso-13a-ui-estudio.md): avisos al empezar y terminar + temporizador de Gradio |
| B-015 | Escalado automático previo de las imágenes de entrada (sobre todo las referencias del renderizador, que cuestan tanto como la salida) si el coste lo hace necesario | [Paso 9](paso-09-pipelines-imagen.md) | Cuando el usuario lo considere necesario | ✅ Cerrado ([factura de octubre](mantenimiento-2026-10-factura.md)): no compensa; FLUX cobra 1 MP por referencia sea cual sea su tamaño |
| B-016 | Revisar en Azure Cost Management lo facturado por los 4 intentos (timeout) de la primera auditoría con `max` (2026-10-18) | [Paso 10](paso-10-auditor-hitl.md) | Cuando haya datos de facturación | ✅ Resuelto ([factura de octubre](mantenimiento-2026-10-factura.md)): el timeout no se facturó (0 €) |
| B-017 | *Background mode* de la Responses API para llamadas de minutos (exige `store=true`) | [Paso 10](paso-10-auditor-hitl.md) | Cuando el usuario lo decida | ⏳ Abierto |
| B-018 | Render final con la misma proporción que la captura (16:9 → 1920×1080) | [Paso 10](paso-10-auditor-hitl.md) | Paso 13b | ✅ Resuelto en [Paso 13b](paso-13b-retoques.md): 1920×1080 exacto (se genera a 1920×1088 y se recorta al centro) |
| B-019 | Incorporar las pruebas de interfaz con Playwright (Edge/Chromium) al repositorio y a la CI | [Paso 11](paso-11-ui-proyectos.md) | Paso 15 | ✅ Resuelto en [Paso 15a](paso-15a-ci-seguridad.md): `e2e/` (pytest-playwright) en la CI con Chromium |
| B-020 | Comprobar con una llamada real si el renderizador acepta tamaños no múltiplos de 16 (p. ej. 1920×1080 directo); hoy se pide el múltiplo superior y se recorta al centro (≈ 0,09 €) | [Paso 13b](paso-13b-retoques.md) | Cuando el usuario lo decida | ⏳ Abierto |
| B-021 | Alerta de gasto de IA por proyecto (umbral configurable) | [Paso 14](paso-14-ui-costes.md) | Cuando el usuario lo considere necesario (hoy son céntimos) | ⏳ Abierto |
| B-022 | Incluir la indexación de referencias (`CONTEXT_MANAGER`) en el coste de la cadena de un render (guardar su `request_id` en la ficha) | [Paso 14](paso-14-ui-costes.md) | Cuando el usuario lo decida (≈ 0,0008 €) | ⏳ Abierto |
| B-023 | Capturas de la interfaz en el README con un caso de uso de demostración, sin marcas registradas (lo prepara el usuario) | [Paso 15b](paso-15b-version-1.md) | Cuando el usuario tenga el caso de uso | ⏳ Abierto |
