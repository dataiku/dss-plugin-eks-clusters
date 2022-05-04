import os, json, logging
from .kubectl_command import run_with_timeout

def install_metrics_server(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'apply', '-f', 'https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml']
    logging.info("Installing Metrics Server with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=30)