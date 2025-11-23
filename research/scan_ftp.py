import json
import os
import time
import ftplib
import logging
import posixpath
import traceback


logging.basicConfig()
log = logging.getLogger('uptpy')
log.setLevel(logging.DEBUG)

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
CREDS_NAME = '_ test_creds.json'
CREDS_FILE = os.path.join(THIS_DIR, CREDS_NAME)



def main():
    with open(CREDS_FILE, encoding='utf8') as file_obj:
        creds = json.load(file_obj)
    # creds['encoding'] = 'latin-1'
    creds['encoding'] = 'cp437'

    ftp = get_ftp(**creds)
    data = scan_remote(ftp, '_private/musike/_swing2')
    print(data)
    with open(os.path.join(THIS_DIR, 'scan_result.json'), 'w', encoding='utf8') as file_obj:
        json.dump(data, file_obj, sort_keys=True, indent=2)



def get_ftp(host, user, passwd, encoding='utf8'):
    # type: (str, str, str) -> ftplib.FTP
    log.info('Connecting to "%s" ...', host)
    try:
        ftp = ftplib.FTP(host, encoding=encoding)
    except Exception as error:
        raise Exception('Error creating connection to "%s"\n%s' % (host, error))

    result = ftp.login(user, passwd)
    log.info(result)
    log.info(ftp.getwelcome())
    return ftp


def scan_remote(ftp, remote_path):
    # type: (ftplib.FTP, str) -> dict[str, dict[str, dict[str, str|int]]]
    log.info('Scanning remote path: %s ...', remote_path)
    data = {}
    t0 = time.time()
    try:
        _scan_remote(ftp, remote_path, '', data)
    except UnicodeDecodeError as error:
        print(traceback.format_exc().strip())
        error

    print('%s took %.3fs' % ('_scan_remote', time.time() - t0))
    return data


def _scan_remote(ftp, root, path, data):
    # type: (ftplib.FTP, str, str, dict[str, dict[str, str]]) -> None
    files = {}
    remote_path = posixpath.join(root, path)
    try:
        for name, item in ftp.mlsd(remote_path):
            if item['type'] == 'file':
                files[name] = {'size': int(item['size'])}
            elif item['type'] == 'dir':
                _scan_remote(ftp, root, posixpath.join(path, name), data)
    except Exception as error:
        print('error on "%s"\n: %s' % (remote_path, error))



    # Collect remote dirs no matter if files or not
    # to be able to delete empty folders.
    data[path] = files
    log.info('dir: %s - %i files', path, len(files))


if __name__ == '__main__':
    main()