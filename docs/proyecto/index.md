# Proyecto

InteriorAI es software libre con [licencia MIT](licencia.md), desarrollado en abierto en
[GitHub](https://github.com/SergioVelmay/InteriorAI).

## Cómo se desarrolla

- **Por pasos.** Cada cambio es un paso con su rama (`feat/paso-NN`), su Pull Request y su
  documento en la
  [bitácora de pasos](https://github.com/SergioVelmay/InteriorAI/tree/main/docs/pasos): objetivo,
  decisiones, implementación, validación y pendientes. Lo diferido va al
  [backlog](https://github.com/SergioVelmay/InteriorAI/blob/main/docs/pasos/BACKLOG.md).
- **Integración continua.** En cada Pull Request, GitHub Actions ejecuta lint, tests, gitleaks
  sobre todo el historial, la construcción de las imágenes Docker, la colección de Postman y las
  pruebas de Playwright, siempre en modo simulación y sin secretos. `main` solo acepta cambios
  con la CI en verde.
- **Versiones** según [SemVer](https://semver.org/lang/es/): cada versión mayor trae cambios
  incompatibles, con sus notas de actualización. Ver [Versiones](versiones.md).
- **Esta documentación** se publica sola en GitHub Pages al integrar cambios en `main`; sus
  fuentes están en la carpeta
  [`docs/`](https://github.com/SergioVelmay/InteriorAI/tree/main/docs) del repositorio (cada
  página tiene un botón para editarla).

## Enlaces

| | |
|---|---|
| Código | <https://github.com/SergioVelmay/InteriorAI> |
| Versiones publicadas | [Releases](https://github.com/SergioVelmay/InteriorAI/releases) |
| Historial de cambios | [CHANGELOG.md](https://github.com/SergioVelmay/InteriorAI/blob/main/CHANGELOG.md) |
| Avisar de un fallo o proponer una mejora | [Issues](https://github.com/SergioVelmay/InteriorAI/issues) |
| Avisar de una vulnerabilidad | [Seguridad](seguridad.md) (en privado) |
