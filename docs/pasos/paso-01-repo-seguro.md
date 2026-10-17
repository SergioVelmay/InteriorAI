# Paso 1 — Repositorio seguro y documentación del agente

## 1. Objetivo

Blindar el repositorio (público) frente a fugas de secretos y datos de usuario, y
crear la documentación modular para el agente antes de escribir código de aplicación.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| `.gitattributes` con `eol=lf` (no estaba en el plan) | Git en Windows convertía a CRLF; los scripts rompen en contenedores Linux. | Confiar en `core.autocrlf` de cada máquina. |
| Defensa en profundidad: `.gitignore` + hooks pre-commit `language: fail` para `.env*` y `data/` | `.gitignore` se salta con `git add -f`; el hook lo bloquea igualmente. | Solo `.gitignore`. |
| `gitleaks` con reglas propias (`.gitleaks.toml`) para claves Azure AI Foundry (32 hex / 84 alfanum.) y endpoints reales `*.services.ai.azure.com`, `*.openai.azure.com`, `*.cognitiveservices.azure.com` | Las reglas por defecto no cubren de forma fiable el formato de Azure; el requisito prohíbe también endpoints. Placeholders `https://<...>.` permitidos. | Reglas por defecto únicamente. |
| Herramientas vía `uvx` (`uvx pre-commit`, `uvx ruff`) | Sin instalaciones globales; coherente con `uv`. pre-commit descarga Go automáticamente para gitleaks. | `pip install pre-commit` global. |
| `ruff.toml` en raíz (no `pyproject.toml`) | El workspace `uv` se define en el Paso 2; así no se adelanta esa decisión. | — |
| `ruff` con reglas `S` (bandit) y `ASYNC` | Seguridad y anti-patrones async detectados en lint. | — |
| `.env.example` incluye ya todas las variables previstas en el plan | Contrato de configuración visible desde el inicio; `AI_PROVIDER_MODE=mock` por defecto. | Añadirlas paso a paso. |
| `.dockerignore` excluye `.env`, `data/`, `docs/` | Evitar que secretos o datos acaben dentro de imágenes. | — |
| Hook `ruff` → id `ruff-check` | Id actual en ruff-pre-commit v0.17. | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `.gitignore` | Secretos, `data/`, venvs, cachés, Gradio, logs, IDE/OS, overrides locales |
| `.gitattributes` | Normalización LF y binarios |
| `.env.example` | Plantilla completa sin valores secretos |
| `.dockerignore` | Exclusiones para builds |
| `.pre-commit-config.yaml` | pre-commit-hooks v6.0.0, ruff v0.17.1, gitleaks v8.30.0, hooks locales anti-`.env`/`data/` |
| `.gitleaks.toml` | Reglas por defecto + reglas Azure |
| `ruff.toml` | Lint y formato |
| `AGENTS.md` | Brief, reglas críticas, estilo, flujo, mapa de rutas |
| `CLAUDE.md` | `@AGENTS.md` + comandos |
| `docs/agent/{azure_foundry,fast_api_specs,gradio_ui}.md` | Contexto técnico por materia (versión de diseño) |
| `README.md` | Mínimo, puesta en marcha |

## 4. Validación

| Prueba | Comando | Resultado |
|--------|---------|-----------|
| Hooks en verde | `uvx pre-commit run --all-files` | ✅ Todos `Passed`/`Skipped` |
| Rutas ignoradas | `git check-ignore -v .env .env.local data/... venv/ .venv/ __pycache__/ .gradio/ secrets.pem` | ✅ Todas ignoradas; `.env.example` no |
| Clave Azure falsa (32 hex y 84 alfanum.) | commit de archivo con clave | ✅ Bloqueado (`azure-ai-foundry-api-key`) |
| Endpoint real | commit con un endpoint `https://` + nombre de recurso real + dominio `services.ai.azure.com` | ✅ Bloqueado (`azure-resource-endpoint`) |
| `.env` forzado | `git add -f .env && git commit` | ✅ Bloqueado (`forbid-env-files`) |
| `data/` forzado | `git add -f data/... && git commit` | ✅ Bloqueado (`forbid-data-dir`) |

## 5. Estado final

✅ Cerrado — rama `feat/paso-01`, validado por el usuario y mergeado a `main`.

## 6. Pendiente / futuro

- Ejecutar gitleaks sobre todo el historial en CI (GitHub Actions) — Paso 15 (B-002).
- Ampliar `CLAUDE.md` con comandos de `uv`, `pytest`, Docker y Postman CLI en Pasos 2, 3 y 5.
