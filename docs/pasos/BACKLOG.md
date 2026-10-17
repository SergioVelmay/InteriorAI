# Backlog consolidado

Elementos diferidos o pendientes de verificación. Cada entrada enlaza al paso que la originó.

| ID | Descripción | Origen | Destino previsto | Estado |
|----|-------------|--------|------------------|--------|
| B-001 | Verificar que el despliegue del Auditor Geométrico acepta `reasoning_effort: max` | [Paso 0](paso-00-plan-y-decisiones.md) | Paso 6 | ⏳ Abierto |
| B-002 | Ejecutar gitleaks sobre todo el historial en CI (GitHub Actions) | [Paso 1](paso-01-repo-seguro.md) | Paso 15 | ⏳ Abierto |
| B-003 | Verificar si la API del renderizador (`/providers/...`) requiere `api-version` | [Paso 2](paso-02-configuracion.md) | Paso 6 | ⏳ Abierto |
| B-004 | Activar Dependabot en GitHub | [Paso 2](paso-02-configuracion.md) | Paso 15 | ⏳ Abierto |
| B-005 | En hosts Linux, `data-init` cambia el propietario de `./data` a uid 1000: hacer configurable el UID/GID (`APP_UID`) si el usuario del host no es 1000 | [Paso 3](paso-03-docker.md) | Paso 15 | ⏳ Abierto |
