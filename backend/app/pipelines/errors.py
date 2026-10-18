"""Errores de los pipelines."""


class PipelineError(Exception):
    """La salida del modelo no es utilizable (p. ej. no cumple el esquema). HTTP 502."""


class PipelineInputError(Exception):
    """Faltan datos para ejecutar el pipeline (p. ej. no hay referencias). HTTP 422."""
