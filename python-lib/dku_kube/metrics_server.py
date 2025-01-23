import os
import json
import logging
import traceback
from .kubectl_command import run_with_timeout, KubeCommandException


def has_metrics_server(kube_config_path):
    env = os.environ.copy()
    env["KUBECONFIG"] = kube_config_path
    cmd = ["kubectl", "get", "pods", "-n", "kube-system", "-l", "app.kubernetes.io/name=metrics-server", "--ignore-not-found"]
    logging.info("Checking metrics server presence with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0


def install_metrics_server_if_needed(kube_config_path):
    if has_metrics_server(kube_config_path):
        logging.info("Metrics server is already deployed on the cluster. Skipping install.")
        return

    try:
        env = os.environ.copy()
        env["KUBECONFIG"] = kube_config_path
        cmd = ["kubectl", "apply", "-f", "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"]
        logging.info("Installing Metrics Server with : %s" % json.dumps(cmd))
        out, err = run_with_timeout(cmd, env=env, timeout=30)
    except KubeCommandException as e:
        logging.warning("Failed to install metrics server: %s" % json.dumps([cmd, e.rv, e.out, e.err]))
        traceback.print_exc()
    except Exception:
        logging.warning("Failed to install metrics server")
        traceback.print_exc()
