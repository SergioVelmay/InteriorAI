# Paso 0 — Plan de acción y decisiones de arquitectura

## 1. Objetivo

Definir y validar con el usuario el plan incremental de InteriorAI, las decisiones
de arquitectura transversales y el flujo de trabajo (ramas, documentación,
herramientas) antes de escribir código.

## 2. Decisiones tomadas

### Decisiones de arquitectura (D1–D5)

| ID | Decisión | Motivo | Alternativa descartada |
|----|----------|--------|------------------------|
| D1 | Telemetría en **dos capas**: middleware HTTP de FastAPI (`request_id` + latencia end-to-end) e **interceptor en el cliente Foundry** (tokens entrada/salida/`reasoning_tokens`, latencia por llamada, coste). Se correlacionan por `request_id`. | Un middleware HTTP no ve la respuesta del proveedor; los tokens solo existen en la respuesta del cliente. | Middleware HTTP único estimando tokens. |
| D2 | **Modo `MOCK`** (`AI_PROVIDER_MODE=mock\|azure`) con respuestas deterministas (texto, imágenes placeholder, tokens simulados). | Cada paso es probable sin credenciales ni coste; habilita CI en un repo público. | Probar siempre contra Azure. |
| D3 | Precios en **`config/pricing.yaml`** (versionado, sin secretos), sobrescribibles por `.env`. Nombres comerciales de modelos solo en `pricing.yaml` y `.env.example`. | Desacoplar código de modelos comerciales; precios cambian. | Tabla de precios en código. |
| D4 | **Escritura atómica** de JSON (temp + `os.replace`) con **lock por proyecto** (`asyncio.Lock` + `filelock`). | Backend y frontend comparten `./data`; evitar corrupción de `proyectos.json` / telemetría. | Escritura directa. |
| D5 | Tema Gradio `gr.themes.Base(primary_hue="zinc", neutral_hue="slate")` + **dark mode forzado** + CSS custom (fondo `#0a0a0a`). | `neutral_950` no es un tema nativo de Gradio; se consigue el look con primitivas soportadas. | — |

### Otras decisiones

| Tema | Decisión |
|------|----------|
| `reasoning_effort` del Auditor Geométrico | Configurable vía `GEOMETRIC_AUDITOR_REASONING_EFFORT` (por defecto `max`). Se **verificará contra la API real en el Paso 6** que el despliegue acepta `max`; si no, se documenta el valor máximo soportado. |
| Ramas git | `main` como rama principal; una rama `feat/paso-NN` por paso; merge a `main` solo tras validación del usuario. |
| Gestor de dependencias | **`uv`** (rápido, lockfile reproducible `uv.lock`). Descartado: `pip` + `requirements.txt`. |
| Documentación | `docs/agent/` = contexto técnico por materia (divulgación progresiva para el agente). `docs/pasos/` = bitácora por paso (decisiones, estado final, pendientes) + `BACKLOG.md` consolidado. |
| Despliegues Azure | El usuario confirma que los 6 despliegues existen con los nombres por defecto (ver tabla de roles). |

### Mapa de roles → despliegues (valores por defecto en `.env.example`)

| Variable de entorno | Despliegue por defecto | Función |
|---------------------|------------------------|---------|
| `DEPLOYMENT_ROLE_PROMPT_ENGINEER` | `gpt-6.1-sol` | Orquestación; notas/planos → prompts técnicos |
| `DEPLOYMENT_ROLE_GEOMETRIC_AUDITOR` | `gpt-6-astra` | QA espacial vs. SketchUp (`reasoning_effort` alto) |
| `DEPLOYMENT_ROLE_CONTEXT_MANAGER` | `gpt-6-luna` | Indexación de catálogos y metadatos |
| `DEPLOYMENT_ROLE_FAST_DRAFT` | `gpt-image-2.5-flare` | Bocetado rápido, iteración cromática |
| `DEPLOYMENT_ROLE_STRUCTURAL_COMPOSER` | `gpt-image-2.5-sunburst` | Composición exacta de mobiliario con cotas |
| `DEPLOYMENT_ROLE_PHOTOREALISTIC_RENDERER` | `FLUX.2-pro` | Render final fotorrealista e inpainting |

## 3. Plan de implementación

| Fase | Paso | Contenido |
|------|------|-----------|
| A — Cimientos | 1 | Repo seguro (`.gitignore`, `.env.example`, pre-commit + gitleaks) y documentación del agente (`AGENTS.md`, `CLAUDE.md`, `docs/agent/`) |
| | 2 | Configuración central con Pydantic Settings (`shared/`) |
| | 3 | Esqueleto Docker (backend + frontend + volumen `studio_shared_data`) |
| B — Datos | 4 | Modelo de dominio y capa de almacenamiento (escritura atómica, índice global) |
| | 5 | API REST de proyectos y assets + colección Postman CLI |
| C — IA y costes | 6 | Abstracción Azure AI Foundry por rol (Azure + Mock) |
| | 7 | Telemetría y control de costes |
| D — Pipelines y HITL | 8 | Pipelines de texto (Context Manager, Prompt Engineer) |
| | 9 | Pipelines de imagen (Draft, Composer, Renderer) |
| | 10 | Auditor geométrico + máquina de estados Human-in-the-Loop |
| E — UI Gradio | 11 | Shell UI, tema y gestión de proyectos |
| | 12 | Pestaña de assets |
| | 13 | Pestaña Estudio (flujo HITL, `gr.ImageEditor`) |
| | 14 | Dashboard de costes |
| F — Release | 15 | Hardening, CI (GitHub Actions), README, revisión de seguridad |

### Estructura de carpetas objetivo

```
InteriorAI/
├── AGENTS.md · CLAUDE.md · README.md · .gitignore · .env.example · .dockerignore
├── docker-compose.yml
├── config/pricing.yaml
├── docs/
│   ├── agent/{azure_foundry.md, fast_api_specs.md, gradio_ui.md}
│   └── pasos/{README.md, BACKLOG.md, paso-NN-*.md}
├── shared/              # settings, modelos Pydantic, enums de roles
├── backend/             # FastAPI: api/, core/, storage/, foundry/, telemetry/, pipelines/, hitl/
├── frontend/            # Gradio: theme, api_client, tabs/
├── postman/             # colección + entorno para Postman CLI
└── data/                # volumen studio_shared_data (gitignored)
```

## 4. Validación

Plan, decisiones D1–D5, flujo de ramas, estructura de carpetas, documentación por
paso y uso de `uv` aprobados explícitamente por el usuario.

## 5. Estado final

✅ Cerrado — rama `main`.

## 6. Pendiente / futuro

- Verificar soporte de `reasoning_effort: max` en el despliegue del Auditor (Paso 6).
