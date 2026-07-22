import os
import json
import logging
import traceback
from dku_aws.aws_command import AwsCommand
from .kubectl_command import run_with_timeout, KubeCommandException


def has_metrics_server_addon(cluster_id, connection_info):
    cmd = ["eks", "describe-addon", "--cluster-name", cluster_id, "--addon-name", "metrics-server"]
    _, return_code, _, err = AwsCommand(cmd, connection_info).run()
    if return_code == 0:
        return True
    if "ResourceNotFoundException" in err:
        return False
    raise Exception("Failed to check whether EKS manages the metrics-server add-on: %s" % err)


def has_metrics_server(kube_config_path):
    env = os.environ.copy()
    env["KUBECONFIG"] = kube_config_path
    cmd = ["kubectl", "get", "deployment", "metrics-server", "-n", "kube-system", "--ignore-not-found", "-o", "name"]
    logging.info("Checking metrics server presence with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0


def install_metrics_server_if_needed(cluster_id, connection_info, kube_config_path):
    cmd = None
    try:
        if has_metrics_server_addon(cluster_id, connection_info) or has_metrics_server(kube_config_path):
            logging.info("Metrics server is already managed or deployed on the cluster. Skipping install.")
            return

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
