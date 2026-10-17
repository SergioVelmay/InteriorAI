# Backlog consolidado

Elementos diferidos o pendientes de verificación. Cada entrada enlaza al paso que la originó.

| ID | Descripción | Origen | Destino previsto | Estado |
|----|-------------|--------|------------------|--------|
| B-001 | Verificar que el despliegue del Auditor Geométrico acepta `reasoning_effort: max` | [Paso 0](paso-00-plan-y-decisiones.md) | Paso 6 | ✅ Resuelto en [Paso 6](paso-06-foundry.md): acepta `max` |
| B-002 | Ejecutar gitleaks sobre todo el historial en CI (GitHub Actions) | [Paso 1](paso-01-repo-seguro.md) | Paso 15 | ⏳ Abierto |
| B-003 | Verificar si la API del renderizador (`/providers/...`) requiere `api-version` | [Paso 2](paso-02-configuracion.md) | Paso 6 | ✅ Resuelto en [Paso 6](paso-06-foundry.md): `api-version=preview` |
| B-004 | Activar Dependabot en GitHub | [Paso 2](paso-02-configuracion.md) | Paso 15 | ⏳ Abierto |
| B-005 | En hosts Linux, `data-init` cambia el propietario de `./data` a uid 1000: hacer configurable el UID/GID (`APP_UID`) si el usuario del host no es 1000 | [Paso 3](paso-03-docker.md) | Paso 15 | ⏳ Abierto |
| B-006 | Detectar assets duplicados por `sha256` al subir (avisar al usuario) | [Paso 4](paso-04-almacenamiento.md) | Paso 5 | ✅ Resuelto en [Paso 5](paso-05-api.md) (409 + `allow_duplicate`) |
| B-007 | Comando para listar/restaurar/vaciar `.papelera/` (siempre con confirmación) | [Paso 4](paso-04-almacenamiento.md) | Paso 15 | ⏳ Abierto |
| B-008 | Actualizar Postman CLI (instalada 1.73.0, disponible 1.75.0) | [Paso 5](paso-05-api.md) | Cuando el usuario lo decida | ⏳ Abierto |
| B-009 | La máscara de GPT-image es orientativa: recomponer en local solo la zona enmascarada para inpainting exacto | [Paso 6](paso-06-foundry.md) | Paso 13 | ⏳ Abierto |
| B-010 | Precios reales de los 6 despliegues para `config/pricing.yaml` (los aporta el usuario) | [Paso 6](paso-06-foundry.md) | Paso 7 | ⏳ Abierto |
