import subprocess

import fb_qt_frontend

# subprocess.DETACHED_PROCESS
# process = subprocess.Popen(cmds, cwd=tool_path)
#     return process.pid
# DETACHED_PROCESS = 0x00000008
# subprocess.Popen([self.nfo['exepath']], creationflags=DETACHED_PROCESS)


if __name__ == '__main__':
    fb_qt_frontend.run()
