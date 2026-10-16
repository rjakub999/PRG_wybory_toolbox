"""Backend selection. Intentionally NO native Esri implementation."""
from typing import Protocol
from .common import DataError

OPERATIONS = ('voronoi', 'neighbors', 'raster')

class GeometryBackend(Protocol):
    def voronoi(self, points, boundary, **options): ...
    def neighbors(self, points, **options): ...
    def raster(self, path, boundary, seeds, **options): ...


def backend(config, operation):
    if operation not in OPERATIONS:
        raise DataError(f'Nieznany moduł: {operation}')
    selected = config.get('backends', {}).get(operation, 'python')
    if selected == 'esri':
        raise DataError(f'{operation}: wariant Esri niezaimplementowany. Nie przełączono automatycznie na Python.')
    if selected != 'python':
        raise DataError(f'Nieznany backend: {selected}')
    from .basic import PythonBackend
    return PythonBackend()
