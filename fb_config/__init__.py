import os
import json

import fb_common

_EXT = '.json'
_DEFAULTS = 'defaults'
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_DEFAULTS_DIR = os.path.join(_THIS_DIR, _DEFAULTS)
DIRNAME = f'.{fb_common.NAME}'

if os.name == 'nt':
    PATH = os.path.join(os.environ['LOCALAPPDATA'], DIRNAME)
elif os.name == 'posix':
    PATH = os.path.join(os.sep, 'etc', DIRNAME)
else:
    raise RuntimeError(f'Unsupported System: {os.name}')


def load_json(json_path: str) -> dict[str, bool | int | str | list[str]]:
    with open(json_path, encoding='utf8') as file_object:
        return json.load(file_object)


def dump_json(json_path: str, data: dict[str, bool | int | str | list[str]]):
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, 'w', encoding='utf8') as file_object:
        return json.dump(data, file_object, indent=2, sort_keys=True)


class _Settings:
    _builtins: list[str] = []

    def __init__(self, name):
        file_name = f'{name}{_EXT}'
        self._user_data_path = os.path.join(PATH, file_name)
        self._defaults = load_json(os.path.join(_DEFAULTS_DIR, file_name))

        self._user_data: dict = {}
        self._time: int | float = 0
        _Settings._builtins[:] = list(self.__dict__)
        self._load_data()

    def _has_user_data(self) -> bool:
        return os.path.isfile(self._user_data_path)

    def _load_data(self) -> None:
        if not self._has_user_data():
            return
        self._user_data.clear()
        self._user_data.update(load_json(self._user_data_path))
        self._time = self._file_time

    @property
    def _file_time(self) -> float:
        if self._has_user_data():
            return os.path.getmtime(self._user_data_path)
        return 0

    def __getattribute__(self, name: str):
        """Handle getting the user preferences.
        For dev ex we want these variables to exist upfront so handle anything!
        Update user data in case there is news.
        """
        try:
            member = super().__getattribute__(name)
        except AttributeError:
            member = None

        if name == '_defaults' or name not in self._defaults:
            return member

        if self._file_time > self._time:
            self._load_data()

        if name in self._user_data:
            member = self._user_data[name]
        elif member is None:
            member = self._defaults[name]

        super().__setattr__(name, member)
        return member

    def __setattr__(self, name, value):
        """Handle setting the user preferences.
        First tho: deal with internal member variables.
        Then create the wanted member vars with `None`.
        Then update user data according to the value.
          If its the same as defaults, remove from user data.
          If no user data left, remove user data file.
        """
        # We need static strings here, no way to gather builtins before :)
        if name in ('_user_data_path', '_defaults') or name not in self._defaults:
            super().__setattr__(name, value)
            return
        # First time creating the member variables.
        if value is None and name in self._defaults:
            super().__setattr__(name, value)
            return
        # Remove value from user data if identical to defaults.
        if name in self._user_data and value == self._defaults[name]:
            del self._user_data[name]
            if not self._user_data and self._has_user_data():
                os.unlink(self._user_data_path)
                return
        # Otherwise just update user data dictionary.
        else:
            self._user_data[name] = value
        dump_json(self._user_data_path, self._user_data)


class _General(_Settings):
    def __init__(self):
        super().__init__('general')

        self.port: int = None

class _Navigation(_Settings):
    def __init__(self):
        super().__init__('navigation')

        self.start_up_directory: str = None
        self.start_up_from_last_directory: bool = None
        self.save_history: bool = None

        self._last_directory: str = None
        self._history: list[str] = None



general = _General()
navigation = _Navigation()


def _check_variables():
    for item in os.scandir(_THIS_DIR):
        if item.is_dir():
            continue
        if not item.name.endswith(_EXT):
            continue
        name = os.path.splitext(item.name)[0]


if __name__ == '__main__':
    _check_variables()
