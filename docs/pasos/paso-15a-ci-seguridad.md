# Paso 15a — CI, Dependabot y seguridad del repositorio

## 1. Objetivo

Que el repositorio público se compruebe solo: integración continua en cada Pull Request
(lint, tests, secretos en todo el historial, imágenes Docker y pruebas de extremo a extremo de la
API y de la interfaz), dependencias al día y protección de `main`. El Paso 15 se divide en
15a (esto) y 15b (contenedores, papelera y versión 1.0.0), a petición del usuario.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **CI en modo mock, sin secretos**, permisos `contents: read`, acciones fijadas por hash (Dependabot las actualiza) | Repositorio público: la CI nunca debe tocar Azure ni exponer nada | Etiquetas mutables (`@v7`) |
| gitleaks sobre **todo el historial** con la imagen oficial fijada por digest (B-002) | Sin licencia ni acción de terceros; mismo `.gitleaks.toml` que el pre-commit | Acción de gitleaks (licencia en organizaciones) |
| **E2E en cada PR** (aprobado): `docker compose up` + colección de Postman con **newman 6.2.3** + Playwright con Chromium (B-019) | Detecta regresiones de interfaz como las encontradas en los Pasos 13-14 | Solo en `main` |
| newman en la CI (Postman CLI en local) | Paquete npm con versión fija, sin instalar con `curl \| sh`; mismo resultado (47 peticiones, 83 comprobaciones) | Instalador de Postman CLI |
| Pruebas E2E en `e2e/` con **pytest-playwright** (grupo `e2e`, fuera de `uv run pytest`) | Reproducibles en local (Edge) y en la CI (Chromium) | Scripts sueltos fuera del repo |
| Cada prueba crea sus proyectos «E2E …» y los mueve a la papelera; **se niegan a ejecutarse fuera de mock** | Nunca generan coste ni tocan proyectos reales | — |
| **Dependabot** semanal y agrupado por ecosistema (uv, Actions, Docker) (B-004) | Una PR por ecosistema y semana | Una PR por paquete |
| **Protección de `main`** (aprobada): PR y CI en verde obligatorias, **sin aprobación obligatoria** | Las PR se crean con la cuenta del usuario y GitHub no deja aprobar las propias | Exigir aprobación |
| Escaneo de secretos de GitHub con **bloqueo en el push** y `SECURITY.md` (aviso privado) | Gratis en repositorios públicos; segunda barrera tras el pre-commit | — |
| Licencia: **MIT** (decidida; se añade en el 15b) | Permisiva; se puede cambiar para versiones futuras | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `.github/workflows/ci.yml` | Trabajos `Lint y tests`, `gitleaks (todo el historial)` y `Docker y extremo a extremo` (trazas de Playwright como artefacto si falla) |
| `.github/dependabot.yml` | uv, GitHub Actions y Docker (`/backend`, `/frontend`) |
| `e2e/conftest.py` | Comprobación de modo mock, `Projects` (proyectos de prueba y limpieza), `UI` (abrir, activar, pestañas, avisos, pintar) |
| `e2e/test_e2e_*.py` | Proyectos, Assets, Estudio (ciclo HITL), retoques (final y composición) y Costes |
| `SECURITY.md` | Cómo avisar, alcance y medidas existentes |
| `pyproject.toml`, `ruff.toml` | Grupo `e2e` (playwright, pytest-playwright); `assert` permitido en `e2e/` |
| `backend/app/telemetry/summary.py`, `frontend/ui/tabs/costs.py` | `project_name` en el resumen (fallo encontrado por las E2E) |
| `README.md`, `CLAUDE.md`, `docs/agent/gradio_ui.md` | Insignia de la CI, comandos y claves de las pruebas E2E |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 333 passed |
| E2E en local contra Docker (mock) | ✅ 5/5 con Edge y 5/5 con Chromium |
| newman en local | ✅ 47 peticiones, 83 comprobaciones |
| gitleaks sobre todo el historial (local) | ✅ 24 commits, sin fugas |
| CI en la PR #15 (2.ª ejecución) | ✅ `Lint y tests` 43 s · `gitleaks` 13 s · `Docker y extremo a extremo` 3 min 32 s (newman 47/83, Playwright 5/5) |
| Configuración de GitHub | ✅ escaneo de secretos con bloqueo en el push, avisos privados de vulnerabilidades, alertas y actualizaciones de seguridad de Dependabot, protección de `main` (PR + 3 comprobaciones, rama al día, sin forzar ni borrar, también para administradores) |

La primera ejecución de la CI falló al montar el volumen: `./data` no existe en un clon limpio
(está en `.gitignore`); la CI la crea antes de `docker compose up` (en el 15b, B-005).

Fallo encontrado por las pruebas E2E: con la simulación oculta y sin llamadas reales, la pestaña
Costes titulaba «Costes de IA de el proyecto» (el nombre salía de los registros). Corregido.

## 5. Estado final

✅ Cerrado — rama `feat/paso-15a`, PR #15 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- Paso 15b: endurecimiento de contenedores, UID/GID configurable (B-005), comando de papelera
  (B-007), README final, LICENSE (MIT), CHANGELOG y versión 1.0.0.
- B-002, B-004 y B-019 cerrados.
