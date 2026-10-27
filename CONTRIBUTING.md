# Cómo contribuir a InteriorAI

¡Gracias por tu interés! Avisos de fallos, ideas, mejoras de la documentación y código son
bienvenidos. Participar en el proyecto supone aceptar su [código de conducta](CODE_OF_CONDUCT.md).

## Avisar de un fallo o proponer una mejora

Abre una [issue](https://github.com/SergioVelmay/InteriorAI/issues/new/choose) con la plantilla
que corresponda. Antes, busca si ya existe una parecida.

- **Nunca pegues tu `.env`, claves ni endpoints de Azure**, ni en el texto ni en capturas.
- Indica la versión y si usas el modo simulación (`mock`) o el de Azure (`azure`).
- Las **vulnerabilidades no se publican en una issue**: sigue la [política de
  seguridad](SECURITY.md) (aviso privado de GitHub).

## Proponer cambios

1. Para cambios grandes, abre antes una issue para comentarlos.
2. Haz un fork y crea una rama desde `main` con un nombre descriptivo (`fix/estimacion-bocetos`,
   `docs/manual-referencias`…).
3. Prepara el entorno y activa las comprobaciones antes de cada commit:

    ```bash
    uv sync
    uvx pre-commit install
    ```

4. Haz el cambio con sus tests y, si cambia el comportamiento, con su documentación.
5. Comprueba que todo pasa:

    ```bash
    uv run pytest
    uv run ruff check . && uv run ruff format --check .
    uv run --group docs mkdocs build --strict   # si tocas docs/ o mkdocs.yml
    ```

6. Abre una Pull Request a `main` con la plantilla. La CI debe quedar en verde.

Todo funciona en **modo simulación**, sin credenciales ni coste: no hace falta una cuenta de
Azure para contribuir, y los tests y la CI nunca llaman a la IA real.

## Reglas del proyecto

Las reglas completas están en [`AGENTS.md`](AGENTS.md); estas no se negocian:

- **Cero secretos en el código.** La configuración se lee de `.env` (nunca versionado); las
  variables nuevas se añaden a `.env.example`, sin valores reales.
- **Cero nombres comerciales de modelo en el código.** La IA se usa por **rol** (`PROMPT_ARCHITECT`,
  `REALISTIC_RENDERER`…) y siempre a través de `FoundryClient`, para que se registre su coste.
- **Todo funciona en modo `mock`.**
- **Supervisión humana:** ninguna etapa avanza sin la elección del usuario, y no se inventan
  medidas.
- **`data/` es del usuario:** nunca se versiona; toda escritura pasa por el repositorio de
  proyectos.

## Convenciones

| Tema | Convención |
|------|------------|
| Código | Python 3.11 con anotaciones de tipos, Pydantic v2, backend asíncrono; `ruff` con líneas de 100 caracteres |
| Idioma | Identificadores en inglés; textos de la interfaz, documentación y commits en español |
| Tests | Junto a cada paquete (`*/tests/`), sin `__init__.py` y con nombres de archivo únicos |
| Commits | `tipo: descripción` (`feat`, `fix`, `docs`, `chore`, `test`, `refactor`) |
| API | Si la cambias, regenera su esquema: `cd backend && uv run python -m app.openapi` |

Más detalle en la sección [Desarrollo](https://sergiovelmay.github.io/InteriorAI/desarrollo/) de
la documentación: entorno, pruebas, CI y herramientas.

## Licencia

Al contribuir aceptas que tu aportación se publique con la [licencia MIT](LICENSE) del proyecto.
