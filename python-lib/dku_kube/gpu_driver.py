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
        tolerations.update([TolerationOrTaint(tol) for tol in nvidia_config['spec']['template']['spec']['tolerations']])

    # Retrieve the tolerations on the daemonset currently deployed to the cluster.
    if has_gpu_driver(kube_config_path):
        cmd = ['kubectl', 'get', 'daemonset', 'nvidia-device-plugin-daemonset', '-n', 'kube-system', '-o', 'jsonpath="{.spec.template.spec.tolerations}"']
        tolerations_raw, err = run_with_timeout(cmd, env=env, timeout=5)
        if _is_none_or_blank(tolerations_raw):
            tolerations.update([TolerationOrTaint(tol) for tol in json.loads(tolerations_raw)])

    # If there are any taints to patch the daemonset with in the node group(s) to create,
    # we add them to the GPU plugin configuration before updating with another `kubectl apply`
    for taint in taints or []:
        # Add the relevant toleration operator
        if taint.get('value', ''):
            taint['operator'] = 'Equal'
        else:
            taint['operator'] = 'Exists'

        # If the toleration is not in the set, add it
        new_toleration = TolerationOrTaint(taint)
        if not tolerations or new_toleration not in tolerations:
            tolerations.add(new_toleration)
    
    # Patch the Nvidia driver configuration with the tolerations derived from node group(s) taints,
    # initial Nvidia driver configuration tolerations and Nvidia daemonset tolerations (when applicable)
    nvidia_config['spec']['template']['spec']['tolerations'] = [toleration.to_dict() for toleration in tolerations]

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

class TolerationOrTaint(dict):
    def __init__(self, tolerationOrTaint):
        if not _is_none_or_blank(tolerationOrTaint.get('key', '')):
            self['key'] = tolerationOrTaint.get('key', '')

        if not _is_none_or_blank(tolerationOrTaint.get('value', '')):
            self['value'] = tolerationOrTaint.get('value', '')

        if not _is_none_or_blank(tolerationOrTaint.get('effect', '')):
            self['effect'] = tolerationOrTaint.get('effect', '')

        if not _is_none_or_blank(tolerationOrTaint.get('operator', '')):
            self['operator'] = tolerationOrTaint.get('operator', '')

    def __eq__(self, other):
        return self.get('key', '') == other.get('key', '') and self.get('value', '') == other.get('value', '') and self.get('effect', '') == other.get('effect', '') and self.get('operator', '') == other.get('operator', '')

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.get('key', ''), self.get('value', ''), self.get('effect', ''), self.get('operator', '')))
    
    def to_dict(self):
        return {k: v for k, v in self.items()}