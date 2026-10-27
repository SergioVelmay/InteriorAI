# Seguridad

## Cómo avisar de una vulnerabilidad

**No abras una issue pública.** Usa el aviso privado de GitHub: pestaña
[**Security → Report a vulnerability**](https://github.com/SergioVelmay/InteriorAI/security/advisories/new)
del repositorio. Indica qué has encontrado, cómo reproducirlo y su posible impacto. Se intenta
responder en un plazo de 7 días.

La política completa está en
[SECURITY.md](https://github.com/SergioVelmay/InteriorAI/blob/main/SECURITY.md).

## Alcance

InteriorAI está pensado para ejecutarse **en local** (puertos solo en `127.0.0.1`) con
credenciales propias de Azure AI Foundry. Son especialmente relevantes:

- La exposición de secretos (`.env`, claves de Azure) en el código, los registros o el historial.
- La lectura o escritura fuera de `data/` (rutas, subidas de archivos).
- Las llamadas a la IA (con coste) sin una acción explícita del usuario.

## Medidas existentes

- **Secretos** solo en `.env` (nunca versionado) y enmascarados en la configuración; gitleaks en
  cada commit y sobre todo el historial en la CI; escaneo de secretos de GitHub con bloqueo en
  el push.
- **Subidas** validadas por su contenido (firma y decodificación completa), con límites de
  tamaño y de píxeles.
- **Contenedores** sin privilegios (usuario 1000), con el sistema de archivos en solo lectura,
  sin capacidades y con límites de memoria y CPU; el frontend sin credenciales y con `data/` en
  solo lectura.
- **Dependencias** vigiladas por Dependabot (Python, acciones de GitHub e imágenes Docker).
