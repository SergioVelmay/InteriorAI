# Pruebas y CI

Todas las pruebas se ejecutan en **modo simulación**: no necesitan credenciales ni generan
coste.

## Tests unitarios y de integración

```bash
uv run pytest
```

| Carpeta | Qué prueba |
|---------|------------|
| `shared/tests/` | Configuración, roles, modelos y reglas comunes |
| `backend/tests/` | API de extremo a extremo con un cliente de IA espía, almacenamiento, migraciones, papelera, telemetría, precios, clientes de Azure (con transporte simulado) y prompts |
| `frontend/tests/` | Vistas, pestañas y cliente de la API, sin abrir el navegador |

## API: colección de Postman

Con la aplicación levantada en modo simulación:

```bash
postman collection run postman/interiorai.postman_collection.json \
  -e postman/local.postman_environment.json --working-dir postman
```

Recorre el flujo completo de la API: proyectos, referencias, fichas, bocetos, composición,
auditoría, retoque, render final, costes y papelera.

## Interfaz: Playwright

Con la aplicación levantada en modo simulación:

```bash
uv run --group e2e playwright install chromium   # una vez
uv run --group e2e pytest e2e                    # o --browser-channel msedge
```

Crean proyectos «E2E …» y los mueven a la papelera al terminar. Se niegan a ejecutarse si el
backend no está en modo simulación.

## Comprobaciones antes de cada commit

`uvx pre-commit install` activa estas comprobaciones:

| Comprobación | Para qué |
|--------------|----------|
| gitleaks | Que no se cuele ningún secreto |
| Bloquear `.env` y `data/` | Que nunca se suban la configuración local ni los datos del usuario |
| ruff (lint y formato) | Estilo y errores comunes |
| Archivos grandes (> 1 MB), conflictos, YAML, TOML, JSON, claves privadas, finales de línea | Higiene del repositorio |

## Integración continua

GitHub Actions ([`.github/workflows/`](https://github.com/SergioVelmay/InteriorAI/tree/main/.github/workflows))
en cada Pull Request y en `main`:

| Trabajo | Qué hace |
|---------|----------|
| Lint y tests | `ruff check`, `ruff format --check` y `pytest` |
| gitleaks (todo el historial) | Busca secretos en todos los commits |
| Docker y extremo a extremo | Construye las imágenes, levanta la aplicación en simulación, ejecuta la colección de Postman (newman) y las pruebas de Playwright |
| Documentación | Construye esta web en modo estricto y, en `main`, la publica en GitHub Pages |

`main` está protegida: solo acepta cambios por Pull Request, con los tres primeros trabajos en
verde y la rama al día. Dependabot propone actualizaciones de Python, de las acciones de GitHub y
de las imágenes Docker; las acciones van fijadas por su SHA.
