import os, json, logging, requests, yaml

from dku_aws.eksctl_command import EksctlCommand
from dku_utils.access import _is_none_or_blank
from .kubectl_command import run_with_timeout

def has_gpu_driver(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'name=nvidia-device-plugin-ds', '--ignore-not-found']
    logging.info('Checking if NVIDIA GPU drivers are installed with : %s' % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_gpu_driver_if_needed(cluster_id, kube_config_path, connection_info, taints):
    # Get the Nvidia driver plugin configuration from the repository
    nvidia_config_raw = requests.get('https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/main/nvidia-device-plugin.yml').text
    nvidia_config = yaml.safe_load(nvidia_config_raw)
    tolerations = set()

    # Get any tolerations from the plugin configuration
    if nvidia_config.get('spec', {}) and nvidia_config['spec'].get('template', {}) and nvidia_config['spec']['template'].get('spec', {}):
        tolerations = set(nvidia_config['spec']['template']['spec']['tolerations'])

    # Retrieve the tolerations on the daemonset currently deployed to the cluster.
    if has_gpu_driver(kube_config_path):
        cmd = ['kubectl', 'get', 'daemonset', 'nvidia-device-plugin-daemonset', '-n', 'kube-system', '-o', 'jsonpath="{.spec.template.spec.tolerations}"']
        tolerations_raw, err = run_with_timeout(cmd, env=env, timeout=5)
        if _is_none_or_blank(tolerations_raw):
            tolerations = tolerations.update(json.loads(tolerations_raw))

    # If there are any taints to patch the daemonset with in the node group(s) to create,
    # we add them to the GPU plugin configuration before updating with another `kubectl apply`
    for taint in taints or []:
        # Add the relevant toleration operator
        if taint.get('value', ''):
            taint['operator'] = 'Equal'
        else:
            taint['operator'] = 'Exists'

        # If the toleration is not in the set, add it
        if taint not in tolerations:
            tolerations.add(taint)
    nvidia_config['spec']['template']['spec']['tolerations'] = list(tolerations)

    # Write the configuration locally
    local_nvidia_plugin_config = os.path.join(os.environ["DIP_HOME"], 'clusters', cluster_id, 'nvidia-device-plugin.yml')
    with open(local_nvidia_plugin_config, "w") as f:
        yaml.safe_dump(nvidia_config, f)

    # Apply the patched Nvidia driver configuration to the cluster
    cmd = ['kubectl', 'apply', '-f', local_nvidia_plugin_config]
    logging.info('Running command to install Nvidia drivers: %s', ' '.join(cmd))
    logging.info('NVIDIA GPU driver config: %s' % yaml.safe_dump(nvidia_config, default_flow_style=False))

    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    run_with_timeout(cmd, env=env, timeout=5)