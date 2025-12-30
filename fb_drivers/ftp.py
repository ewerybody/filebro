def matches(path: str) -> bool:
    """ Tell if we're asking for an FTP path."""
    path = path.lstrip()
    if not path:
        return False
    if path.startswith('ftp://'):
        return True
    return False
