# Paso 37 — Comunidad del repositorio

## 1. Objetivo

Sexto paso del [plan de la versión 4.0.0](plan-version-4.md): completar los estándares de
comunidad de GitHub (B-102; el perfil estaba al 57 %) y los ajustes del repositorio.

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Alcance | Guía de contribución, código de conducta, plantillas de issues y de PR, página «Contribuir» en la web, web y temas del repositorio, Wiki desactivada |
| Ajustes visibles en GitHub | Aplicados por Claude con `gh` (OK del usuario) |
| Projects y Discussions | Projects desactivado (no se usaba); Discussions sigue desactivado: las dudas, por issues |
| Contacto del código de conducta | Las herramientas de GitHub («Report content» y la moderación del administrador), sin correo público (el de los commits es el *noreply* de GitHub) |
| B-104 y B-105 | Al Paso 38, que ya trata los costes |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| `CONTRIBUTING.md` | Cómo avisar de fallos y proponer mejoras (sin secretos; vulnerabilidades en privado), cómo proponer cambios (fork, rama, comprobaciones, PR), reglas no negociables resumidas, convenciones y licencia de las aportaciones. El detalle técnico, enlazado a la sección Desarrollo de la web |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, traducción oficial al español, con el método de contacto |
| Plantillas de issues | Formularios `error.yml` (qué pasa, cómo reproducirlo, versión, modo de la IA, Docker o uv, registros; aviso de no pegar secretos) y `mejora.yml` (necesidad, propuesta, alternativas, principios). Sin issues en blanco; enlaces a la documentación y al aviso privado de vulnerabilidades (`config.yml`) |
| Plantilla de PR | Resumen, cómo se ha probado y lista de comprobación (tests, pre-commit, sin secretos ni nombres de modelo, modo simulación, documentación y esquema de la API, commits) |
| Web | Página **Proyecto › Contribuir** y enlace en la portada de Proyecto |
| README | Sección «Contribuir» con la guía y el código de conducta |
| Repositorio (`gh repo edit`) | Web: <https://sergiovelmay.github.io/InteriorAI/>; temas: `interior-design`, `generative-ai`, `human-in-the-loop`, `fastapi`, `gradio`, `azure-ai-foundry`, `python`, `docker`; Wiki (sin páginas) y Projects desactivados |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `mkdocs build --strict` | ✅ Sin avisos |
| `uv run pytest` | ✅ |
| pre-commit | ✅ (incluye `check yaml` sobre las plantillas) |
| Ajustes del repositorio | ✅ Comprobados con `gh repo view` |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-37`.

## 6. Pendiente / futuro

- Tras el merge: comprobar el perfil de comunidad (`/community`) y las plantillas en «New issue».
- Paso 38: precios y costes con la factura real (B-098), con B-104 y B-105.
