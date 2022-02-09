import sys, os, subprocess, logging, json, requests, shutil
from .eksctl_loader import get_eksctl_or_fetch
from dku_utils.access import _has_not_blank_property, _convert_to_string

class EksctlCommand(object):
    def __init__(self, args, connection_info):
        self.args = args
        self.eksctl_bin = get_eksctl_or_fetch()
        self.env = os.environ.copy()
        if _has_not_blank_property(connection_info, 'accessKey'):
            self.env['AWS_ACCESS_KEY_ID'] = connection_info['accessKey']
        if _has_not_blank_property(connection_info, 'secretKey'):
            self.env['AWS_SECRET_ACCESS_KEY'] = connection_info['secretKey']
        if _has_not_blank_property(connection_info, 'sessionToken'):
            self.env['AWS_SESSION_TOKEN'] = connection_info['sessionToken']
        if _has_not_blank_property(connection_info, 'region'):
            self.env['AWS_DEFAULT_REGION'] = connection_info['region']
        
    def run(self):
        cmd = _convert_to_string([self.eksctl_bin] + self.args)
        logging.info('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd,
                             shell=False,
                             env=self.env,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True)
        (o, e) = p.communicate()
        rv = p.wait()
        return (cmd, rv, o, e)

    def run_and_get_output(self):
        return self.run()[2]
    
    def run_and_log(self):
        cmd = _convert_to_string([self.eksctl_bin] + self.args)
        logging.info('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd,
                             shell=False,
                             env=self.env,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             universal_newlines=True)
        with p.stdout as s:
            for line in iter(s.readline, ''):
                logging.info(line.rstrip())
        return p.wait()
    
    def run_and_get(self):
        cmd = _convert_to_string([self.eksctl_bin] + self.args)
        logging.info('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd,
                             shell=False,
                             env=self.env,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True)
        out, err = p.communicate()
        rv = p.wait()
        return rv, out, err
