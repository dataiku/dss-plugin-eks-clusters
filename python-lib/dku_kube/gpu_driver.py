import os, sys, json, yaml, logging, random, time

from dku_aws.eksctl_command import EksctlCommand
from .kubectl_command import run_with_timeout

def has_gpu_driver(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'name=nvidia-device-plugin-ds', '--ignore-not-found']
    logging.info("Checking if NVIDIA GPU drivers are installed with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_gpu_driver_if_needed(cluster_id, kube_config_path, connection_info, nodes_to_label):
    if not check_eksctl_version(connection_info):
        label_gpu_nodes(kube_config_path, nodes_to_label)
        
        if not has_gpu_driver(kube_config_path):
            gpudriver_file_path = kube_config_path.replace("kube_config", "nvidia_driver.yaml")

            with open(gpudriver_file_path, 'w') as f:
                f.write(get_gpu_driver_def())
            cmd = ['kubectl', 'apply', '-f', os.path.abspath(gpudriver_file_path)]

            logging.info("Install NVIDIA GPU drivers with : %s" % json.dumps(cmd))
            env = os.environ.copy()
            env['KUBECONFIG'] = kube_config_path
            run_with_timeout(cmd, env=env, timeout=5)
        
def check_eksctl_version(connection_info):
    args = ["version"]
    c = EksctlCommand(args, connection_info)
    o = c.run_and_get_output()
    
    return o >= "0.32.0"

def label_gpu_nodes(kube_config_path, nodes):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    
    for node in nodes:
        if node:
            cmd = ["kubectl", "label", "node", node, "nvidia.com/gpu=1"]
            logging.info("Labeling node %s for NVIDIA GPU Drivers" % node)
            
            run_with_timeout(cmd, env=env, timeout=5)
            
def get_gpu_driver_def():
    yaml = """
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-daemonset
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-device-plugin-ds
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      # This annotation is deprecated. Kept here for backward compatibility
      # See https://kubernetes.io/docs/tasks/administer-cluster/guaranteed-scheduling-critical-addon-pods/
      annotations:
        scheduler.alpha.kubernetes.io/critical-pod: ""
      labels:
        name: nvidia-device-plugin-ds
    spec:
      nodeSelector:
        nvidia.com/gpu: "1"
      tolerations:
      # This toleration is deprecated. Kept here for backward compatibility
      # See https://kubernetes.io/docs/tasks/administer-cluster/guaranteed-scheduling-critical-addon-pods/
      - key: CriticalAddonsOnly
        operator: Exists
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      # Mark this pod as a critical add-on; when enabled, the critical add-on
      # scheduler reserves resources for critical add-on pods so that they can
      # be rescheduled after a failure.
      # See https://kubernetes.io/docs/tasks/administer-cluster/guaranteed-scheduling-critical-addon-pods/
      priorityClassName: "system-node-critical"
      containers:
      - image: nvidia/k8s-device-plugin:v0.7.3
        name: nvidia-device-plugin-ctr
        args: ["--fail-on-init-error=false"]
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        volumeMounts:
          - name: device-plugin
            mountPath: /var/lib/kubelet/device-plugins
      volumes:
        - name: device-plugin
          hostPath:
            path: /var/lib/kubelet/device-plugins    
    """
    return yaml