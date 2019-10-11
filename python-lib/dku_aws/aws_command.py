import sys, os, subprocess, logging, json, requests, shutil
from dku_utils.access import _has_not_blank_property

class AwsCommand(object):
    def __init__(self, args, connection_info):
        self.args = args
        self.env = os.environ.copy()
        if _has_not_blank_property(connection_info, 'accessKey'):
            self.env['AWS_ACCESS_KEY_ID'] = connection_info['accessKey']
        if _has_not_blank_property(connection_info, 'secretKey'):
            self.env['AWS_SECRET_ACCESS_KEY'] = connection_info['secretKey']
        if _has_not_blank_property(connection_info, 'region'):
            self.env['AWS_DEFAULT_REGION'] = connection_info['region']
        
    def run_and_get_output(self):
        cmd = ["aws"] + self.args
        print('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd, shell=False, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (o, e) = p.communicate()
        return o
    
    def run_and_log(self):
        cmd = ["aws"] + self.args
        print('Running %s' % (' '.join(cmd)))
        p = subprocess.Popen(cmd, shell=False, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with p.stdout as s:
            for line in iter(s.readline, b''):
                logging.info(line)
        return p.wait()