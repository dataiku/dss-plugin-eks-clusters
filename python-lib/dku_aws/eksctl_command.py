import sys, os, subprocess, logging, json, requests, shutil
from .eksctl_loader import get_eksctl_or_fetch
from dku_utils.access import _has_not_blank_property

class EksctlCommand(object):
    def __init__(self, args, connection_info):
        self.args = args
        self.eksctl_bin = get_eksctl_or_fetch()
        self.env = os.environ.copy()
        if _has_not_blank_property(connection_info, 'accessKey'):
            self.env['AWS_ACCESS_KEY_ID'] = connection_info['accessKey']
        if _has_not_blank_property(connection_info, 'secretKey'):
            self.env['AWS_SECRET_ACCESS_KEY'] = connection_info['secretKey']
        if _has_not_blank_property(connection_info, 'region'):
            self.env['AWS_DEFAULT_REGION'] = connection_info['region']
        
    def run_and_get_output(self):
        cmd = [self.eksctl_bin] + self.args
        print('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd, shell=False, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (o, e) = p.communicate()
        return o
    
    def run_and_log(self):
        cmd = [self.eksctl_bin] + self.args
        print('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd, shell=False, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with p.stdout as s:
            for line in iter(s.readline, b''):
                logging.info(line)
        return p.wait()
    
    def run_and_get(self):
        cmd = [self.eksctl_bin] + self.args
        print('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd, shell=False, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        rv = p.wait()
        return rv, out, err
