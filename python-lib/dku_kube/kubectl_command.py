import os, sys, json, yaml, logging, subprocess, time

class KubeCommandException(Exception):
    def __init__(self, message, out, err):
        super(KubeCommandException, self).__init__(message)
        self.out = out
        self.err = err
        
def run_with_timeout(cmd, env=None, timeout=3, nokill=False):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    waited = 0
    while waited < timeout and p.poll() is None:
        time.sleep(1)
        waited += 1
    if p.poll() is None:
        if nokill:
            return None, None
        else:
            p.kill()
            raise Exception("Process did not finish after %s" % timeout)
    out, err = p.communicate()
    rv = p.wait()
    if rv != 0:
        raise KubeCommandException("Command failed with %s" % rv, out, err)
    return out, err


