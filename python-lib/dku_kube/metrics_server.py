import os, json, logging, traceback
from .kubectl_command import run_with_timeout, KubeCommandException

def install_metrics_server(kube_config_path):
    try:
        env = os.environ.copy()
        env['KUBECONFIG'] = kube_config_path
        cmd = ['kubectl', 'apply', '-f', 'https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml']
        logging.info("Installing Metrics Server with : %s" % json.dumps(cmd))
        out, err = run_with_timeout(cmd, env=env, timeout=30)
    except KubeCommandException as e:
        logging.warning('Failed to install metrics server: %s' % json.dumps([cmd, e.rv, e.out, e.err]))
        traceback.print_exc()
    except Exception:
        logging.warning('Failed to install metrics server')
        traceback.print_exc()
