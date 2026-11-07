# Flujo de trabajo para tareas y nuevas funcionalidades

Este documento describe el ciclo operativo que sigue un agente al trabajar en InteriorAI. Para
las reglas críticas y el mapa del proyecto, lee primero [`AGENTS.md`](../../AGENTS.md) y
[`CLAUDE.md`](../../CLAUDE.md). Consulta los documentos técnicos de `docs/agent/` solo cuando
aplique el área del cambio.

## 1. Recibir y entender la petición

Las peticiones suelen llegar en español y pueden mezclar una observación, una pregunta y varios
cambios. Identifica qué comportamiento pide el usuario, qué problema intenta resolver y qué queda
fuera de alcance. No conviertas una pregunta o un análisis en cambios de código sin autorización.

Antes de proponer una solución, comprueba el estado real del repositorio y lee la implementación,
las pruebas y la documentación relacionadas. No deduzcas cómo funciona una parte por su nombre ni
por conversaciones anteriores. Si el árbol tiene cambios locales, revísalos y consérvalos; no los
pises ni los reviertas.

Para una propuesta grande, consulta o abre primero una issue, como indica
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). Busca también issues existentes para no duplicar una
petición.

Como mínimo, revisa:

- `AGENTS.md` y `CLAUDE.md` en la raíz.
- `git branch --show-current`, `git status --short --branch` y los commits recientes.
- La entrada correspondiente de `docs/pasos/BACKLOG.md`, si existe, y el índice de
  `docs/pasos/README.md`.
- El código, los tests y la documentación del área afectada.
- `.pre-commit-config.yaml` y los workflows de `.github/workflows/` cuando prepares la validación.

Comprueba la rama antes de cualquier operación de Git. No trabajes directamente en `main`, no
empujes a `main` y no borres ramas. Si la rama o el árbol no están en el estado esperado, detente y
acláralo antes de cambiar de rama.

## 2. Registrar la petición en el backlog

Busca primero si el hallazgo ya está registrado. Cada hallazgo o petición que requiera trabajo debe
tener una fila en `docs/pasos/BACKLOG.md` con el siguiente identificador correlativo `B-NNN`. La
tabla tiene estas columnas:

| Columna | Qué registrar |
|---------|---------------|
| ID | Identificador correlativo `B-NNN` |
| Descripción | Problema o resultado solicitado, en términos verificables |
| Origen | Issue, observación, revisión o petición del usuario en chat/sesión; indica fecha cuando se conozca |
| Destino previsto | Paso que lo abordará o `Sin fecha` si aún no se prioriza |
| Estado | `⏳ Abierto`, detalle pendiente o `✅ Resuelto en el Paso NN` una vez integrado |

No dupliques una entrada existente: actualízala y enlázala al paso que la resuelve. No marques una
entrada como resuelta antes de que el cambio esté mergeado en `main`.

## 3. Proponer el plan y esperar autorización

Antes de implementar, presenta un plan breve pero concreto. Indica qué pasos hacen falta, qué
incluye cada uno, qué archivos o capas podrían cambiar, cómo se probará, qué documentación se
actualizará y qué queda fuera. Si hay llamadas reales a IA, indica el número y tipo de llamadas y
su coste estimado.

Espera el visto bueno explícito del usuario antes de empezar a implementar. La autorización de una
tarea no autoriza por sí sola cambios de alcance, llamadas facturables, publicación de versiones ni
otras acciones que requieran aprobación explícita.

## 4. Resolver dudas y dejar decisiones trazables

Pregunta antes de elegir cuando haya ambigüedad o varias alternativas con criterios distintos.
Presenta las opciones y una recomendación razonada; no inventes requisitos, medidas ni decisiones.
El usuario suele responder con una lista numerada de decisiones. Resume esas decisiones en el
documento del paso para que no dependan del historial del chat.

## 5. Implementar en incrementos

Después del OK, sincroniza las referencias de `origin` y crea una rama nueva `feat/paso-NN` desde
`origin/main` actualizado. Trabaja en cambios pequeños, compatibles con la arquitectura y las
convenciones del área. Si cambias una firma, busca todos sus llamantes y verifica los recorridos que
no cubren los tests unitarios; separa responsabilidades cuando dos flujos necesiten contratos
distintos, en vez de parchear una llamada rota a ciegas.

Respeta las reglas de [`AGENTS.md`](../../AGENTS.md): configuración desde `.env` sin versionarlo,
IA por rol y a través de `FoundryClient`, escrituras en `data/` con `ProjectRepository`, backend
asíncrono y transiciones HITL solo por acción del usuario.

## 6. Añadir pruebas adecuadas

Todo comportamiento nuevo necesita pruebas en el nivel que puede detectar sus fallos:

- Añade o actualiza tests junto al paquete (`shared/tests/`, `backend/tests/` o `frontend/tests/`),
  sin `__init__.py` y con nombres únicos en el repositorio.
- Si cambia la interfaz, añade pruebas Playwright en `e2e/` para los recorridos visibles en el
  navegador. Los tests unitarios de UI llaman directamente a manejadores: no demuestran que los
  eventos estén conectados, que no haya bucles ni que la actualización ocurra en el navegador.
- Usa fixtures sintéticas para E2E; no hagas depender una prueba de los proyectos privados de
  `data/`.
- Si cambia la API, actualiza las pruebas y regenera `docs/referencia/openapi.json` desde
  `backend/` con `uv run python -m app.openapi`.

La experiencia del Paso 50 mostró que cientos de tests unitarios pueden pasar mientras una llamada
de retoque queda rota por una firma antigua; Playwright detectó el fallo. Elige una prueba de
extremo a extremo cuando el defecto solo se manifieste en el flujo integrado.

## 7. Mantener la documentación junto al cambio

Todo paso tiene su documento `docs/pasos/paso-NN-*.md` y una fila en
[`docs/pasos/README.md`](../pasos/README.md). Usa las seis secciones de la plantilla del índice:

1. Objetivo.
2. Decisiones tomadas.
3. Implementación.
4. Validación con comandos y resultados reales.
5. Estado final.
6. Pendiente / futuro, replicado en el backlog.

Se pueden usar subsecciones para análisis, resultados o decisiones complejas; conserva las seis
secciones principales y no afirmes una validación que no hayas ejecutado o consultado.

Si cambia la interfaz, revisa también las páginas afectadas de `docs/manual/`,
`docs/referencia/interfaz.md` y `docs/agent/gradio_ui.md`. Asegúrate de que el texto y las capturas
describan la misma interfaz. Las capturas del manual son parte de la presentación pública: se
guardan en `docs/manual/img/`, en JPG y por debajo de 1 MB. Se toman navegando en modo `mock` sobre
proyectos y renders reales ya existentes, sin generar imágenes; las pruebas E2E usan datos
sintéticos. Si una captura exige cambiar el estado de un proyecto, déjalo como estaba al terminar.

No dejes imágenes sueltas en la raíz del repositorio. El hook `forbid-data-dir` protege `data/` y
las imágenes de la raíz, aunque sean pequeñas; las capturas versionables van dentro de
`docs/manual/img/`.

## 8. Validar y comunicar resultados comprobables

Por defecto, todas las pruebas y el trabajo manual van en `AI_PROVIDER_MODE=mock`, sin credenciales
ni coste. El usuario es quien cambia el modo de su `.env`. Nunca hagas una llamada real a Azure
sin anunciar antes la llamada y su coste estimado y recibir el OK explícito del usuario. No cambies
el `.env` para habilitarla. Redondea las estimaciones de coste hacia arriba.

Ejecuta las comprobaciones pertinentes y comunica la salida real, no una expectativa:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --group docs mkdocs build --strict
uvx pre-commit run --all-files
```

Cuando cambie la interfaz, levanta la aplicación aislada en `mock` y ejecuta además las pruebas
E2E, por ejemplo en Edge local:

```bash
uv run --group e2e pytest e2e --browser-channel msedge
```

La CI usa Chromium. Distingue lo que ejecutaste en local de los resultados de CI. Si una prueba no
se pudo ejecutar, déjala como pendiente con el motivo; no escribas «✅ pasa» ni atribuyas un fallo a
una causa que no hayas comprobado.

El pre-commit puede modificar archivos (Ruff usa `--fix`): después de ejecutarlo, revisa de nuevo
`git status` y el diff completo. Sus controles incluyen secretos, archivos grandes, formato,
conflictos, YAML/TOML/JSON y las prohibiciones de versionar `.env`, `data/` e imágenes sueltas.

## 9. Preparar commit y Pull Request

Antes de cada operación de Git, confirma la rama y revisa el diff. No incluyas datos, capturas con
secretos, `.env` ni cambios ajenos a la tarea. Los mensajes de commit se escriben en español con
`tipo: descripción` (`feat`, `fix`, `docs`, `chore`, `test` o `refactor`); el cuerpo explica por
qué se hizo el cambio. Añade la línea de coautoría del agente que realmente participó, sin copiar
la identidad de otro agente. Ejemplo:

```text
docs: paso 53 - documentar el flujo de trabajo

Explica por qué queda documentado el ciclo de trabajo.

Co-authored-by: OpenCode <noreply@opencode.ai>
```

Abre la Pull Request a `main` solo cuando el usuario haya autorizado la tarea y el cambio esté
validado. Usa [.github/pull_request_template.md](../../.github/pull_request_template.md) y deja
claro:

- Qué entra y por qué.
- Cómo se ha probado, con comandos y resultados reales.
- Qué comprobaciones pasan, cuáles no se pudieron ejecutar y qué queda pendiente.
- Que no hay secretos ni datos privados y, cuando aplique, que se trabajó en `mock`.

No abras una PR solo para pedir permiso sobre un plan que todavía no ha recibido OK. Una vez abierta,
no la merges: la revisa y la mergea el usuario.

## 10. CI, revisión y cierre

Consulta los checks de la PR en GitHub. La CI actual ejecuta lint y tests, gitleaks sobre el
historial y Docker con la colección Postman/Newman y Playwright; el workflow de documentación
construye MkDocs en modo estricto cuando corresponde. En una PR, la publicación de Pages puede
figurar como omitida: se publica al integrar en `main`.

Cuando haya resultados, añade al documento del paso una fila `CI de la PR #N` con los trabajos y
su resultado real. Corrige fallos y vuelve a comprobar la CI después de cada cambio. Envía al
usuario un resumen con el alcance, la validación, los checks, los pendientes y el enlace a la PR; a
continuación espera su revisión. No merges, no empujes a `main`, no borres ramas y no crees etiquetas
ni Releases sin el OK explícito.

Después de que el usuario mergee:

1. Actualiza las referencias y verifica que el merge está en `main`.
2. Reconstruye Docker con `docker compose up --build -d` y comprueba el estado y el healthcheck.
3. Actualiza el estado del documento y del índice a `✅ Cerrado`, anotando rama, PR y commit de
   integración. Marca como resueltas las entradas de backlog que ese paso completó; conserva
   abiertas las que sigan pendientes.
4. Informa al usuario del cierre. La publicación de versiones, etiquetas y Releases sigue
   requiriendo autorización explícita.

## Lista de verificación

- [ ] Leí `AGENTS.md`, `CLAUDE.md` y el contexto técnico aplicable.
- [ ] Verifiqué rama, árbol de trabajo, código, tests, commits recientes y backlog; no asumí cómo funciona.
- [ ] Registré la petición nueva o enlacé la entrada existente; propuse alcance y coste y esperé el OK.
- [ ] Pregunté las dudas y guardé las decisiones del usuario en el documento del paso.
- [ ] Creé la rama del paso desde `origin/main` actualizado y añadí pruebas para el comportamiento nuevo.
- [ ] Actualicé el documento del paso, su índice, backlog y documentación afectada.
- [ ] Ejecuté las validaciones aplicables y anoté solo resultados observados; Azure siguió en `mock` salvo OK explícito.
- [ ] Revisé el diff, los secretos, `data/`, capturas, el commit y su coautoría.
- [ ] Abrí la PR con resultados y pendientes claros; comprobé la CI y esperé a que el usuario la revise y mergee.
- [ ] Después del merge, reconstruí Docker, verifiqué el healthcheck y cerré el paso y el backlog correspondiente.
