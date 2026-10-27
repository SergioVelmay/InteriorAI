# Paso 35 — Referencia técnica

## 1. Objetivo

Cuarto paso del [plan de la versión 4.0.0](plan-version-4.md): la referencia técnica de la web
pública, con la API y su Swagger, y una sección de desarrollo (B-100).

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Swagger | Swagger UI embebido en la web, solo de consulta («Try it out» desactivado: la web es estática); para probar, el Swagger local |
| Esquema OpenAPI | Exportado de FastAPI a `docs/referencia/openapi.json`, versionado, con un test que falla si no está al día (los cambios de la API se ven en el diff de la PR) |
| Desarrollo | Pestaña propia, separada de la referencia |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Exportación del esquema | `backend/app/openapi.py` (`python -m app.openapi`): genera el esquema en modo mock, sin `.env` ni `data/`, y lo escribe en `docs/referencia/openapi.json`. Test `test_api_openapi_export.py`: el publicado coincide con la API, cada endpoint está en un grupo descrito y no quedan rutas de la v1 |
| Metadatos de la API | Descripción, contacto, licencia y descripción de cada grupo de endpoints (`OPENAPI_TAGS`), visibles también en el Swagger local |
| Swagger en la web | Plugin `mkdocs-swagger-ui-tag` (grupo `docs`): grupos plegados, filtro, sin envío de peticiones; sigue el modo oscuro o claro de la web |
| Referencia técnica | **Arquitectura** (contenedores, recorrido de una generación en un diagrama de secuencia, principios de diseño, estructura del código); **API REST** (convenciones, códigos de error, endpoints por grupos, ejemplo con `curl` y el Swagger); **Datos y almacenamiento** (modelo de datos con diagrama, los 12 grupos de la receta, etapas y estados, carpeta `data/`, escritura atómica, papelera, migraciones); **IA y costes** (roles y superficies de API, cliente de IA, reintentos y tiempos, prompts de sistema y automáticos, cálculo del coste y de la cadena); **Interfaz** (pestañas, comportamiento común, editor de máscara, tema y textos) |
| Desarrollo | **Entorno y convenciones** (uv workspace, ejecutar sin Docker, convenciones, flujo de trabajo, documentación); **Pruebas y CI** (pytest, Postman, Playwright, pre-commit, trabajos de la CI); **Operación y herramientas** (CLI de almacenamiento, telemetría simulada, prueba real de Azure, configuración, esquema de la API) |
| `docs/agent/fast_api_specs.md` | Al día: carpetas y modelos sin la v1, esquema exportado y auditoría sin la captura de la v1 |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ (incluye los 2 tests nuevos del esquema) |
| `mkdocs build --strict` | ✅ Sin avisos |
| Revisión visual (`mkdocs serve`, Playwright) | ✅ Swagger embebido en modo oscuro con los 7 grupos descritos; diagramas de contenedores, de secuencia y de datos dibujados. El de secuencia fallaba por un punto y coma en un mensaje (en Mermaid separa instrucciones): corregido |
| pre-commit | ✅ |
| CI de la PR #50 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-35`.

## 6. Pendiente / futuro

- Paso 36: manual de usuario con el caso «Cocina Abierta para Manual de Usuario».
