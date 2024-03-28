import os, json, logging, requests, yaml

from dku_aws.eksctl_command import EksctlCommand
from .kubectl_command import run_with_timeout

def has_gpu_driver(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'name=nvidia-device-plugin-ds', '--ignore-not-found']
    logging.info('Checking if NVIDIA GPU drivers are installed with : %s' % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_gpu_driver_if_needed(cluster_id, kube_config_path, connection_info, taints):
    if not has_gpu_driver(kube_config_path) and not check_eksctl_version(connection_info):
        nvidia_config_raw = requests.get('https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/main/nvidia-device-plugin.yml').text
    else:
        cmd = ['kubectl', 'describe', 'daemonset']
        nvidia_config_raw, err = run_with_timeout(cmd, env=env, timeout=5)

    local_nvidia_plugin_config = os.path.join(os.environ["DIP_HOME"], 'clusters', cluster_id, 'nvidia-device-plugin.yml')
    nvidia_config = yaml.safe_load(nvidia_config_raw)

    if taints and nvidia_config.get('spec', {}) and nvidia_config['spec'].get('template', {}) and nvidia_config['spec']['template'].get('spec', {}):
        tolerations = nvidia_config['spec']['template']['spec'].get('tolerations', [])

        # If there are any taints to patch the daemonset with,
        # We add them to the GPU plugin configuration before updating with another `kubectl apply`
        for taint in taints:
            # Add the relevant toleration operator
            if taint.get('value', ''):
                taint['operator'] = 'Equal'
            else:
                taint['operator'] = 'Exists'

            # If the toleration is not in the list, add it
            if taint in tolerations:
                tolerations.append(taint)

    with open(local_nvidia_plugin_config, "w") as f:
        yaml.safe_dump(nvidia_config, f)

    cmd = ['kubectl', 'apply', '-f', local_nvidia_plugin_config]
    logging.info('Running command to install Nvidia drivers: %s', ' '.join(cmd))
    logging.info('NVIDIA GPU driver config: %s' % yaml.safe_dump(nvidia_config, default_flow_style=False))

    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    run_with_timeout(cmd, env=env, timeout=5)
        
def check_eksctl_version(connection_info):
    args = ['version']
    c = EksctlCommand(args, connection_info)
    o = c.run_and_get_output()
    
    return o >= '0.32.0'