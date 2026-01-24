# import hashlib

NAME = 'filebro'
# KEY = hashlib.md5(NAME.encode()).hexdigest()
KEY = b'\xeb\x90;id\xc6\x8aH\x1c\x10\xae\xf9\x98\xfcB_'
CHECK = b'\xe2\x9c\x94'.decode()

CORE_WORKERS = 2
QUEUE_THRESHOLD = 5
