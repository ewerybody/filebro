import os
import sys
# import subprocess

try:
    import fb_qt_backend
except ImportError:
    this_dir = os.path.abspath(os.path.dirname(__file__))
    project_dir = os.path.join(this_dir, 'proto')
    sys.path.append(project_dir)
    # print(f'os.getcwd(): {os.getcwd()}')
    # print(f'this_dir: {this_dir}')
    # print('\n'.join(sys.path))
    import fb_qt_backend

# subprocess.DETACHED_PROCESS
# process = subprocess.Popen(cmds, cwd=tool_path)
#     return process.pid
# DETACHED_PROCESS = 0x00000008
# subprocess.Popen([self.nfo['exepath']], creationflags=DETACHED_PROCESS)


if __name__ == '__main__':
    fb_qt_backend.run()
