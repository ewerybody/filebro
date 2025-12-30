import os
import string


if os.name == 'nt':
    import string

    def matches(path: str) -> bool:
        """Tell if we're asking for a local Windows filesystem path."""
        path = path.lstrip()
        if len(path) < 2:
            return False
        if path.startswith('file://'):
            return True
        path = os.path.expandvars(os.path.expanduser(path))
        if path[0].lower() in string.ascii_lowercase and path[1] == ':':
            return True
        return os.path.isabs(path)

elif os.name == 'posix':

    def matches(path: str) -> bool:
        """Tell if we're asking for a local Linux filesystem path."""
        path = path.lstrip()
        if not path:
            return False
        if path.startswith('file://'):
            return True
        roots = ['/' + i.name for i in os.scandir('/') if i.is_dir()]
        path = os.path.expandvars(os.path.expanduser(path))
        if any(path.startswith(r) for r in roots):
            return True
        return os.path.isabs(path)


def lookup(path: str, specs=None):
    files = []
    dirs = []
    details = {}

    path = path.lstrip()
    if len(path) < 2:
        return files, dirs, details

    path = os.path.expandvars(os.path.expanduser(path))
    if path[0].lower() in string.ascii_lowercase and path[1] == ':':
        path += '/'

    for item in os.scandir(path):
        if item.is_dir():
            dirs.append(item.name)
        elif item.is_file():
            files.append(item.name)
        else:
            raise RuntimeError(f'What is "{path}"?!?!')
    return files, dirs, details
