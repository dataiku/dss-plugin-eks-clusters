import os, json, logging

from dku_aws.eksctl_command import EksctlCommand
from .kubectl_command import run_with_timeout

def has_gpu_driver(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'name=nvidia-device-plugin-ds', '--ignore-not-found']
    logging.info("Checking if NVIDIA GPU drivers are installed with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_gpu_driver_if_needed(cluster_id, kube_config_path, connection_info):
    if not has_gpu_driver(kube_config_path) and not check_eksctl_version(connection_info):
        cmd = ['kubectl', 'apply', '-f', "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/master/nvidia-device-plugin.yml"]

        logging.info("Install NVIDIA GPU drivers with : %s" % json.dumps(cmd))
        env = os.environ.copy()
        env['KUBECONFIG'] = kube_config_path
        run_with_timeout(cmd, env=env, timeout=5)
        
def check_eksctl_version(connection_info):
    args = ["version"]
    c = EksctlCommand(args, connection_info)
    o = c.run_and_get_output()
    
    return o >= "0.32.0"