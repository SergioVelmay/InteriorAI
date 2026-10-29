# Versiones

InteriorAI sigue el [versionado semántico](https://semver.org/lang/es/): `MAYOR.MENOR.PARCHE`.
Una versión **mayor** trae cambios incompatibles (de configuración, de datos o de la API) y
explica cómo actualizar; los datos se migran solos al arrancar.

El detalle de cada versión está en el
[CHANGELOG](https://github.com/SergioVelmay/InteriorAI/blob/main/CHANGELOG.md) y en las
[Releases de GitHub](https://github.com/SergioVelmay/InteriorAI/releases).

| Versión | Fecha | Lo principal |
|---------|-------|--------------|
| [4.0.0](https://github.com/SergioVelmay/InteriorAI/releases/tag/v4.0.0) | 2026-10-29 | Prompts más precisos, sin la compatibilidad con la v1 (esquema de datos v3), esta documentación y precios contrastados con la factura real |
| [3.0.0](https://github.com/SergioVelmay/InteriorAI/releases/tag/v3.0.0) | 2026-10-27 | Pulido completo de la interfaz tras un caso real y roles con nombres nuevos |
| [2.0.0](https://github.com/SergioVelmay/InteriorAI/releases/tag/v2.0.0) | 2026-10-25 | Rediseño del flujo: referencias analizadas (receta y ficha), prompts automáticos y tres pestañas de estudio |
| [1.0.0](https://github.com/SergioVelmay/InteriorAI/releases/tag/v1.0.0) | 2026-10-18 | Primera versión: brief de diseño, bocetos, composición y render final |

## Cómo actualizar

```bash
git pull
docker compose up --build -d
```

### Desde la 3.x a la 4.0.0

Los datos pasan solos al esquema v3 al arrancar; cada proyecto guarda una copia en
`metadatos.v2.json`. Las imágenes de la v1 siguen en sus galerías como imágenes sueltas, sin su
brief. Desaparecen los endpoints `/briefs` de la API. La variable `PROMPT_ARCHITECT_TIMEOUT_S` es
nueva y opcional (300 s por defecto).

### Desde la 2.x a la 3.0.0

Los roles cambian de nombre, también en las variables del `.env` (`DEPLOYMENT_ROLE_*`,
`*_REASONING_EFFORT` y `GEOMETRY_AUDITOR_TIMEOUT_S`). Renómbralas; si queda alguna con el nombre
anterior, la aplicación avisa al arrancar y no la usa.

| Antes (hasta la 2.0.0) | Desde la 3.0.0 |
|------------------------|----------------|
| `PROMPT_ENGINEER` | `PROMPT_ARCHITECT` |
| `FAST_DRAFT` | `FAST_DRAFT_MAKER` |
| `STRUCTURAL_COMPOSER` | `COMPOSITION_BUILDER` |
| `PHOTOREALISTIC_RENDERER` | `REALISTIC_RENDERER` |
| `GEOMETRIC_AUDITOR` | `GEOMETRY_AUDITOR` |
| `REFERENCE_ANALYST` | (sin cambios) |

### Desde la 1.0.0

La 4.0.0 ya no lee los datos de la 1.0.0: actualiza antes con la 3.0.0 (`git checkout v3.0.0`,
arranca para que migre los datos) y después a la última.
