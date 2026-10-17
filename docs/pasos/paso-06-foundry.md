# Paso 6 — Abstracción de Azure AI Foundry por rol

## 1. Objetivo

Un único cliente de IA, usado solo por rol, con dos implementaciones intercambiables según
`AI_PROVIDER_MODE` (`mock` sin coste / `azure` real), cuyos resultados ya incluyen todo lo que
necesita la telemetría de costes; y verificar cada despliegue real con un plan de llamadas
mínimo aprobado por el usuario.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **SDK oficial `openai`** para `/openai/v1` (Responses e Images) + **`httpx`** para el renderizador (aprobado por el usuario) | El SDK resuelve reintentos, tipos y `usage`; la API del proveedor es distinta. | `httpx` para todo. |
| **Doble seguro** en el script de verificación: modo `azure` + confirmación `s` por llamada (aprobado) | El interruptor de `.env` sigue siendo una protección real de costes. | Script independiente del modo. |
| **Claude lanza la verificación** tras activar el usuario el modo `azure`, anunciando cada llamada (aprobado) | El usuario monitoriza; las llamadas se limitan al plan. | Ejecución por el usuario. |
| Interfaz `FoundryClient` (plantilla): valida rol ↔ operación antes de delegar | Errores inmediatos, sin coste, si se usa un rol para lo que no es. | Validación en cada implementación. |
| Resultados con `role`, `deployment`, `latency_s` y `Usage` (entrada/salida/razonamiento) | El Paso 7 envolverá el cliente sin cambiar a sus usuarios. | Telemetría dentro de cada llamada. |
| `FoundryError.usage`: una respuesta incompleta o JSON inválido conserva los tokens | Se facturan igualmente; la telemetría debe registrarlos. | Perder el uso en errores. |
| Renderizador: `edit_image` = edición por **referencias** (≤ 8), sin máscara (`FoundryUnsupportedError` que remite a `STRUCTURAL_COMPOSER`) | FLUX.2-pro no admite inpainting con máscara (documentación oficial). | — |
| `AZURE_FOUNDRY_RENDERER_API_VERSION=preview` (por defecto en código) | La API del proveedor la exige (cierra B-003). | Reutilizar `AZURE_FOUNDRY_API_VERSION` (la API v1 no la usa). |
| Una petición por imagen en el renderizador (`seed + i`) | La API devuelve una imagen por llamada. | — |
| Mock con tokens simulados y PNG etiquetados | Permite desarrollar telemetría y UI sin coste. | Mock sin uso. |
| **`openai` 3.x usa `httpx2`**: el SDK con su propio cliente; `httpx` declarado explícitamente; en tests, transporte simulado para cada librería | Detectado al arrancar en modo azure: faltaba `httpx` en la imagen y se pasaba al SDK un cliente de otra librería. | Compartir cliente. |
| **Los Dockerfiles importan todos los módulos al construir** (`RUN python -c "import ..."`) | Los imports diferidos (solo en modo azure) no se ejercitan en mock: ahora una dependencia ausente rompe el build. | Descubrirlo en runtime. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `backend/app/foundry/{types,errors,base,mock,azure,smoke,__init__}.py` | Cliente, tipos, errores, simulación, implementación real y verificación |
| `backend/app/main.py`, `backend/app/api/deps.py` | `app.state.foundry` (cerrado al apagar), `FoundryDep` |
| `shared/src/shared/settings.py`, `.env.example` | `AZURE_FOUNDRY_RENDERER_API_VERSION` |
| `backend/pyproject.toml` | `openai>=3.0`, `httpx>=0.27` |
| `backend/Dockerfile`, `frontend/Dockerfile` | Comprobación de imports en el build |
| `backend/tests/test_foundry_{mock,azure,smoke}.py` | 16 + 18 + 5 tests |
| `docs/agent/azure_foundry.md` | Reescrito con lo implementado y lo verificado |

## 4. Validación

### Tests (sin red)

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 160 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `docker compose build` (con comprobación de imports) | ✅ |
| Script en modo mock dentro del contenedor | ✅ `Bloqueado`, exit 2 |

Cubierto: mock determinista, JSON por esquema, PNG válidos, máscara aplicada solo en la zona,
tokens simulados; control rol ↔ operación; rutas exactas, cabecera `Bearer`, `store=False`,
`reasoning.effort` solo en el auditor, `json_schema` estricto, lectura de `reasoning_tokens`,
respuesta incompleta con uso, multipart con máscara, cuerpo del renderizador (`seed`, referencias,
`api-version`), respuestas por `url`, reintento con `Retry-After`; traducción de 401/403/429/
filtro de contenido/400 sin filtrar la clave; script: bloqueo en mock, «n» omite todo, plan
completo con mock, filtro por rol y fallback del auditor a `high`.

### Verificación real contra Azure AI Foundry (usuario en modo `azure`)

| # | Rol → despliegue | Resultado | Latencia | Tokens entrada / salida / razonamiento |
|---|------------------|-----------|----------|----------------------------------------|
| 1 | PROMPT_ENGINEER → gpt-6.1-sol | ✅ Frase en español coherente | 6,11 s | 44 / 65 / 0 |
| 2 | CONTEXT_MANAGER → gpt-6-luna | ✅ `{"estilo":"escandinavo","colores":["gris claro","roble"]}` | 3,86 s | 83 / 64 / 37 |
| 3 | GEOMETRIC_AUDITOR → gpt-6-astra (`max`) | ✅ Razonamiento espacial correcto (puerta y tramo continuo) | 22,96 s | 74 / 1.084 / 1.012 |
| 4 | FAST_DRAFT → gpt-image-2.5-flare | ✅ Acuarela nórdica 1024×1024 PNG | 14,54 s | 24 / 196 / 0 |
| 5 | STRUCTURAL_COMPOSER → gpt-image-2.5-sunburst | ✅ Sofá añadido; ventana y pared conservadas | 18,43 s | 1.053 / 196 / 0 |
| 6 | PHOTOREALISTIC_RENDERER → FLUX.2-pro | ✅ Render fotorrealista 1024×1024 JPEG | 34,47 s | — (por imagen) |

6 llamadas, sin llamadas fuera del plan (la 3b no fue necesaria).

Hallazgos:
- **B-001 resuelto**: gpt-6-astra acepta `reasoning_effort=max`; el 93 % de su salida es razonamiento.
- **B-003 resuelto**: el renderizador funciona con `api-version=preview` y el nombre del despliegue tal cual (`FLUX.2-pro`), sin pasarlo a minúsculas.
- gpt-6-luna razona por defecto (37 tokens) sin pedirlo → margen en `max_output_tokens`.
- **La máscara de GPT-image es orientativa**: el sofá ocupó ~x 60–960 con máscara en x 200–824 → B-009.

Problemas detectados y resueltos durante el paso:
1. Backend en bucle de reinicio al activar `azure`: `ModuleNotFoundError: httpx` (el SDK 3.x usa
   `httpx2`). Detectado antes de cualquier llamada real → dependencia explícita, clientes separados
   y comprobación de imports en el build.

## 5. Estado final

🧪 En validación — rama `feat/paso-06`, Pull Request en GitHub.

## 6. Pendiente / futuro

- B-009: recomposición local para inpainting exacto (solo píxeles de la máscara) (Paso 13).
- B-010: precios reales de los 6 despliegues para `config/pricing.yaml` (Paso 7).
- El informe del script se sobrescribe en cada ejecución (`informe.json`); valorar un nombre con
  fecha si se usa a menudo.
