import os
import types
import importlib

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_LIB_NAME = os.path.basename(_THIS_DIR)


def get_all() -> dict[str, types.ModuleType]:
    """ Import all available driver modules."""
    drivers: dict[str, types.ModuleType] = {}
    for item in os.scandir(_THIS_DIR):
        if item.is_dir() or item.name == '__init__.py':
            continue
        base, ext = os.path.splitext(item.name)
        if ext.lower() != '.py':
            continue
        module = importlib.import_module(f'{_LIB_NAME}.{base}')
        drivers[base] = module
    return drivers


class NeedAuthentication(Exception):
    pass


if __name__ == '__main__':
    get_all()
