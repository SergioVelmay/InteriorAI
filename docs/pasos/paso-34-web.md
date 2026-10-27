# Paso 34 — Web de documentación

## 1. Objetivo

Tercer paso del [plan de la versión 4.0.0](plan-version-4.md): una web pública de documentación
en GitHub Pages, con la estructura completa y las primeras páginas (B-099). El manual de usuario
(Paso 36) y la referencia técnica (Paso 35) se escriben después.

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Dónde | GitHub Pages con MkDocs Material (no la Wiki ni solo Markdown en el repositorio) |
| Idioma | Solo español |
| Contenido | Manual de usuario, referencia técnica (backend, API y Swagger) y lo habitual de un proyecto en GitHub (versiones, seguridad, licencia) |
| Versiones de la documentación | Una sola (la de `main`), con una página de versiones que enlaza el CHANGELOG y las Releases |
| GitHub Pages | Lo activa Claude |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| `mkdocs.yml` | Material en español, modo oscuro y claro según el sistema, pestañas de navegación, buscador, botón de editar cada página, copiar código, diagramas mermaid e imágenes ampliables (`mkdocs-glightbox`). `docs_dir: docs`, sin `docs/agent/` ni `docs/pasos/` (se consultan en el repositorio) |
| Dependencias | Grupo `docs` de uv (`mkdocs-material`, `mkdocs-glightbox`), aparte de la aplicación |
| Páginas | **Inicio** (qué es, portada, tarjetas, cómo funciona, principios); **Primeros pasos** (modos, requisitos, instalación con Docker, actualización, comandos, problemas frecuentes y configuración del `.env` variable a variable); **Proyecto** (cómo se desarrolla, versiones con notas de actualización, seguridad y licencia); **Manual** y **Referencia técnica** con su contenido previsto |
| Portada | `docs/img/portada-render-final.jpg`, recortada de la captura del render final |
| Publicación | `.github/workflows/docs.yml`: construcción estricta (`mkdocs build --strict`) en cada PR que toque la documentación y publicación en GitHub Pages al integrar en `main`; acciones fijadas por SHA |
| GitHub Pages | Activado con `build_type: workflow` (entorno `github-pages`, solo desde `main`): <https://sergiovelmay.github.io/InteriorAI/> |
| Otros | Enlace a la web en el README; `AGENTS.md` y `CLAUDE.md` con la web y sus comandos; `check-yaml --unsafe` en pre-commit (etiquetas `!!python/name` de `mkdocs.yml`); `/site/` en `.gitignore` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run --locked --only-group docs mkdocs build --strict` | ✅ Sin avisos |
| Revisión visual con `mkdocs serve` (Playwright) | ✅ Inicio en modo oscuro y claro, configuración (tablas sin partir los nombres de variable), instalación y versiones |
| pre-commit | ✅ |

Coste real del paso: 0 €.

Aviso de la herramienta: **Material for MkDocs llega al fin de su vida el 5 de mayo de 2027**
(arreglos críticos hasta entonces). Su sucesor, Zensical, es del mismo equipo y lee el mismo
`mkdocs.yml`: queda en el backlog (B-103).

## 5. Estado final

⏳ En revisión — rama `feat/paso-34`. La web se publica al mergear la PR.

## 6. Pendiente / futuro

- Paso 35: referencia técnica (arquitectura, API con Swagger, modelo de datos, IA y costes,
  desarrollo).
- Paso 36: manual de usuario con el caso «Cocina Abierta para Manual de Usuario».
- B-103: migrar a Zensical antes de mayo de 2027.
