import os, json, logging, yaml
from .kubectl_command import run_with_timeout
from dku_utils.access import _is_none_or_blank
from dku_utils.tools_version import strip_kubernetes_version
from dku_utils.taints import Toleration

AUTOSCALER_IMAGES = {
    '1.24': 'v1.24.3',
    '1.25': 'v1.25.3',
    '1.26': 'v1.26.4',
    '1.27': 'v1.27.3',
    '1.28': 'v1.28.0'
}

def has_autoscaler(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'app=cluster-autoscaler', '--ignore-not-found']
    logging.info("Checking autoscaler presence with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_autoscaler_if_needed(cluster_id, cluster_config, cluster_def, kube_config_path, taints):
    if not has_autoscaler(kube_config_path):
      kubernetes_version = cluster_config.get("k8sVersion", None)
      if _is_none_or_blank(kubernetes_version):
          kubernetes_version = cluster_def.get("Version")

      kubernetes_version = strip_kubernetes_version(kubernetes_version)
      autoscaler_file_path = 'autoscaler.yaml'

      if float(kubernetes_version) < 1.24:
          autoscaler_image = AUTOSCALER_IMAGES.get('1.24', 'v1.24.3')
      else:  
          autoscaler_image = AUTOSCALER_IMAGES.get(kubernetes_version, 'v1.28.0')

      autoscaler_full_config = list(yaml.safe_load_all(get_autoscaler_roles()))
      autoscaler_config = yaml.safe_load(get_autoscaler_config(cluster_id, autoscaler_image))
      tolerations = set()

      # If there are any taints to patch the autoscaler with in the node group(s) to create,
      # we add them to the autoscaler configuration before updating with another `kubectl apply`
      tolerations.update(Toleration.from_dict(taints))

      # Patch the autoscaler with the tolerations derived from node group(s) taints if any
      if tolerations:
          autoscaler_config['spec']['template']['spec']['tolerations'] = Toleration.to_list(tolerations)
          logging.debug('Autoscaler deployment config: %s' % yaml.safe_dump(autoscaler_config, default_flow_style=False))

      autoscaler_full_config.append(autoscaler_config)
      logging.debug('Autoscaler complete config: %s' % yaml.safe_dump_all(autoscaler_full_config, default_flow_style=False))

      with open(autoscaler_file_path, "w") as f:
          yaml.safe_dump_all(autoscaler_full_config, f, explicit_start=True)

      env = os.environ.copy()
      env['KUBECONFIG'] = kube_config_path
      cmd = ['kubectl', 'create', '-f', os.path.abspath(autoscaler_file_path)]
      logging.info("Create autoscaler with : %s" % json.dumps(cmd))
      run_with_timeout(cmd, env=env, timeout=5)
        
def get_autoscaler_roles():
    # the auto-discovery version from https://github.com/kubernetes/autoscaler/tree/master/cluster-autoscaler/cloudprovider/aws
    # all the necessary roles and tags are handled by eksctl with the --asg-access flag
    return """
---
apiVersion: v1
kind: ServiceAccount
metadata:
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
  name: cluster-autoscaler
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-autoscaler
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
rules:
  - apiGroups: [""]
    resources: ["events", "endpoints"]
    verbs: ["create", "patch"]
  - apiGroups: [""]
    resources: ["pods/eviction"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/status"]
    verbs: ["update"]
  - apiGroups: [""]
    resources: ["endpoints"]
    resourceNames: ["cluster-autoscaler"]
    verbs: ["get", "update"]
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["watch", "list", "get", "update"]
  - apiGroups: [""]
    resources:
      - "namespaces"
      - "pods"
      - "services"
      - "replicationcontrollers"
      - "persistentvolumeclaims"
      - "persistentvolumes"
    verbs: ["watch", "list", "get"]
  - apiGroups: ["extensions"]
    resources: ["replicasets", "daemonsets"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["watch", "list"]
  - apiGroups: ["apps"]
    resources: ["statefulsets", "replicasets", "daemonsets"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses", "csinodes", "csidrivers", "csistoragecapacities"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["batch", "extensions"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch", "patch"]
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["create"]
  - apiGroups: ["coordination.k8s.io"]
    resourceNames: ["cluster-autoscaler"]
    resources: ["leases"]
    verbs: ["get", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["create","list","watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["cluster-autoscaler-status", "cluster-autoscaler-priority-expander"]
    verbs: ["delete", "get", "update", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cluster-autoscaler
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-autoscaler
subjects:
  - kind: ServiceAccount
    name: cluster-autoscaler
    namespace: kube-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: cluster-autoscaler
subjects:
  - kind: ServiceAccount
    name: cluster-autoscaler
    namespace: kube-system
"""

def get_autoscaler_config(cluster_id, autoscaler_image_version):
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    app: cluster-autoscaler
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cluster-autoscaler
  template:
    metadata:
      labels:
        app: cluster-autoscaler
    spec:
      serviceAccountName: cluster-autoscaler
      containers:
        - image: registry.k8s.io/autoscaling/cluster-autoscaler:%(autoscalerimageversion)s
          name: cluster-autoscaler
          resources:
            limits:
              cpu: 100m
              memory: 600Mi
            requests:
              cpu: 100m
              memory: 600Mi
          command:
            - ./cluster-autoscaler
            - --v=4
            - --stderrthreshold=info
            - --cloud-provider=aws
            - --skip-nodes-with-local-storage=false
            - --expander=least-waste
            - --node-group-auto-discovery=asg:tag=k8s.io/cluster-autoscaler/enabled,k8s.io/cluster-autoscaler/%(clusterid)s
          volumeMounts:
            - name: ssl-certs
              mountPath: /etc/ssl/certs/ca-certificates.crt #/etc/ssl/certs/ca-bundle.crt for Amazon Linux Worker Nodes
              readOnly: true
          imagePullPolicy: "Always"
      volumes:
        - name: ssl-certs
          hostPath:
            path: "/etc/ssl/certs/ca-bundle.crt"
""" % {'autoscalerimageversion': autoscaler_image_version, 'clusterid': cluster_id}