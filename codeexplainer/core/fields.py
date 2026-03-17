from __future__ import annotations

import json

from django.db import models


def serialize_vector(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    components = [float(component) for component in value]
    return "[" + ",".join(f"{component:.8f}" for component in components) + "]"


class VectorField(models.Field):
    description = "pgvector-backed embedding field"

    def __init__(self, *args, dimensions: int, **kwargs):
        self.dimensions = dimensions
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["dimensions"] = self.dimensions
        return name, path, args, kwargs

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return f"vector({self.dimensions})"
        return "text"

    def get_prep_value(self, value):
        return serialize_vector(value)

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None or isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return [float(component) for component in value]

        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            try:
                return [float(component) for component in json.loads(normalized)]
            except Exception:
                normalized = normalized.strip("[]")
                if not normalized:
                    return []
                return [float(component.strip()) for component in normalized.split(",")]

        return [float(component) for component in value]
