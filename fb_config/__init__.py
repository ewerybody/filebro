"""
FileBro configuration/settings subsystem.
"""

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
        self.port_range: int = None


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
    defaults = {}
    for item in os.scandir(_DEFAULTS_DIR):
        if not item.is_file():
            continue
        base, ext = os.path.splitext(item.name)
        if ext.lower() != _EXT:
            continue
        defaults[base] = load_json(item.path)

    with open(__file__) as file_obj:
        content = file_obj.read()

    # get code in chunks, except for generated ones
    chunks = []
    insert_index: int = -1
    this_chunk = []
    for i, line in enumerate(content.split('\n')):
        if not any(line.startswith(x) for x in ('def ', 'class ', 'if __name__ == ')):
            this_chunk.append(line)
            continue

        if not this_chunk[0].startswith('class _') or not this_chunk[0].endswith(
            '(_Settings):'
        ):
            chunks.append(this_chunk.copy())
        elif insert_index == -1:
            insert_index = len(chunks)

        this_chunk.clear()
        this_chunk.append(line)

    chunks.append(this_chunk.copy())

    # generate target classes code
    i4 = ' ' * 4
    i8 = 2 * i4
    for name, data in defaults.items():
        this_chunk.clear()
        this_chunk.append(f'class _{name.title()}(_Settings):')
        this_chunk.append(f'{i4}def __init__(self):')
        this_chunk.append(f"{i8}super().__init__('{name}')")
        this_chunk.append('')
        for key, value in data.items():
            this_chunk.append(f'{i8}self.{key}: {_get_type_string(value)} = None')
        this_chunk.append('')
        this_chunk.append('')

        chunks.insert(insert_index, this_chunk.copy())
        insert_index += 1

    this_chunk.clear()
    for name in defaults:
        this_chunk.append(f'{name} = _{name.title()}()')
    chunks.insert(insert_index, this_chunk)

    new_content = '\n'.join(line for ch in chunks for line in ch)
    if new_content == content:
        print(f'{fb_common.CHECK} Nothing new!')
        return

    base, ext = os.path.splitext(__file__)
    new_file_path = f'{base}_new{ext}'
    with open(new_file_path, 'w', encoding='utf8') as file_obj:
        file_obj.write(new_content)
    print(f'{fb_common.CHECK} new content in:\n  {new_file_path}')


def _get_type_string(value: bool | float | int | str | list | dict) -> str:
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, str):
        return 'str'
    if isinstance(value, dict):
        return 'dict'
    if isinstance(value, list):
        if not value:
            return 'list'
        types: set[str] = set()
        for element in value:
            subtype = _get_type_string(element)
            if subtype in ('list', 'dict'):
                continue
            types.add(subtype)
        return f'list[{", ".join(types)}]'


if __name__ == '__main__':
    _check_variables()
