# Política de seguridad

## Cómo avisar de una vulnerabilidad

**No abras una issue pública.** Usa el aviso privado de GitHub:
pestaña **Security → Report a vulnerability** de este repositorio. Indica qué has encontrado,
cómo reproducirlo y su posible impacto. Intentaré responder en un plazo de 7 días.

## Alcance

InteriorAI está pensado para ejecutarse **en local** (puertos publicados solo en `127.0.0.1`)
con credenciales propias de Azure AI Foundry. Son especialmente relevantes:

- Exposición de secretos (`.env`, claves de Azure) en el código, los logs o el historial.
- Lectura o escritura fuera de `data/` (rutas, subidas de archivos).
- Llamadas a la IA (con coste) sin la acción explícita del usuario.

## Medidas existentes

- Secretos solo en `.env` (nunca versionado) y `SecretStr` en la configuración; gitleaks en
  pre-commit y sobre todo el historial en la CI; escaneo de secretos de GitHub con bloqueo en
  el push.
- Subidas validadas por contenido (firma y decodificación completa), con límites de tamaño y de
  píxeles.
- Contenedores sin privilegios (uid 1000); el frontend sin credenciales y con `data/` en solo
  lectura.
- Dependabot para dependencias de Python, acciones de GitHub e imágenes Docker.
