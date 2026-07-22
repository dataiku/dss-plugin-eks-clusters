import os
import json
import logging
import re
import requests
import yaml
from .kubectl_command import run_with_timeout
from dku_utils.access import _is_none_or_blank
from dku_utils.tools_version import parse_kubernetes_version, strip_kubernetes_version
from dku_utils.taints import Toleration
from oras.provider import Registry


AUTOSCALER_IMAGE_REPOSITORY = "autoscaling/cluster-autoscaler"
AUTOSCALER_TAG_RE = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")

# Used only when registry tag discovery is unavailable, which preserves the
# existing custom-registry workflow for registries that do not expose tags/list.
# Keep values pinned to tags known to exist in registry.k8s.io.
# fmt: off
AUTOSCALER_IMAGE_FALLBACKS = {
    "1.24": "v1.24.3",
    "1.25": "v1.25.3",
    "1.26": "v1.26.4",
    "1.27": "v1.27.3",
    "1.28": "v1.28.0",
    "1.29": "v1.29.5",
    "1.30": "v1.30.7",
    "1.31": "v1.31.5",
    "1.32": "v1.32.7",
    "1.33": "v1.33.4",
    "1.34": "v1.34.3",
    "1.35": "v1.35.0",
}
# fmt: on
k8s_image_client = Registry()


def has_autoscaler(kube_config_path):
    env = os.environ.copy()
    env["KUBECONFIG"] = kube_config_path
    cmd = ["kubectl", "get", "pods", "--namespace", "kube-system", "-l", "app=cluster-autoscaler", "--ignore-not-found"]
    logging.info("Checking autoscaler presence with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0


def _parse_autoscaler_tag(tag):
    match = AUTOSCALER_TAG_RE.match(tag)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _discover_published_autoscaler_tags(autoscaler_registry_url):
    repository_url = "/".join(path_part.strip("/") for path_part in [autoscaler_registry_url, AUTOSCALER_IMAGE_REPOSITORY])
    logging.info("Retrieving published cluster autoscaler image tags from %s" % repository_url)

    return [tag for tag in k8s_image_client.get_tags(repository_url) if _parse_autoscaler_tag(tag) is not None]


def _select_matching_autoscaler_tag_from_tags(tags, parsed_kubernetes_minor):
    matching_tags = []
    for tag in tags:
        parsed_tag = _parse_autoscaler_tag(tag)
        if parsed_tag is not None and parsed_tag[:2] == parsed_kubernetes_minor:
            matching_tags.append((parsed_tag, tag))

    if matching_tags:
        matching_tags.sort()
        return matching_tags[-1][1]


def select_autoscaler_image(kubernetes_version, autoscaler_registry_url, autoscaler_image_tag_override=None):
    kubernetes_major, kubernetes_minor, kubernetes_version_string = parse_kubernetes_version(kubernetes_version)
    parsed_kubernetes_minor = (kubernetes_major, kubernetes_minor)

    if not _is_none_or_blank(autoscaler_image_tag_override):
        autoscaler_image_tag_override = autoscaler_image_tag_override.strip()
        logging.info(
            "Using configured cluster autoscaler image tag override %s for Kubernetes %s" % (autoscaler_image_tag_override, kubernetes_version_string)
        )
        return autoscaler_image_tag_override

    try:
        published_tags = _discover_published_autoscaler_tags(autoscaler_registry_url)
    except (requests.RequestException, ValueError) as e:
        logging.warning(
            "Unable to retrieve published cluster autoscaler image tags from registry %s. Fallback will be used.\n %s." % (autoscaler_registry_url, e)
        )
    else:
        selected_tag = _select_matching_autoscaler_tag_from_tags(published_tags, parsed_kubernetes_minor)
        if selected_tag is None:
            logging.warning(
                "No published cluster autoscaler image tag matches Kubernetes %s in registry %s. Fallback will be used."
                % (
                    kubernetes_version_string,
                    autoscaler_registry_url,
                )
            )
        else:
            logging.info("Using cluster autoscaler image tag %s for Kubernetes %s" % (selected_tag, kubernetes_version_string))
            return selected_tag

    fallback_tags = list(AUTOSCALER_IMAGE_FALLBACKS.values())
    fallback_tag = _select_matching_autoscaler_tag_from_tags(fallback_tags, parsed_kubernetes_minor)
    if fallback_tag is not None:
        logging.info("Using bundled fallback tag %s for Kubernetes %s." % (fallback_tag, kubernetes_version_string))
        return fallback_tag

    latest_supported_version = sorted(AUTOSCALER_IMAGE_FALLBACKS.keys(), key=lambda version: tuple(int(part) for part in version.split(".")))[-1]
    latest_fallback_tag = AUTOSCALER_IMAGE_FALLBACKS[latest_supported_version]
    logging.info(
        "No bundled fallback matches Kubernetes %s. Using latest bundled fallback tag %s instead."
        % (
            kubernetes_version_string,
            latest_fallback_tag,
        )
    )
    return latest_fallback_tag


def add_autoscaler_if_needed(cluster_id, cluster_config, cluster_def, kube_config_path, taints, autoscaler_registry_url, aws_region):
    if not has_autoscaler(kube_config_path):
        kubernetes_version = cluster_config.get("k8sVersion", None)
        if _is_none_or_blank(kubernetes_version) or kubernetes_version.strip().lower() == "latest":
            kubernetes_version = cluster_def.get("Version")
        if _is_none_or_blank(kubernetes_version):
            raise Exception("No Kubernetes version found in cluster config or EKS cluster definition")

        kubernetes_version = strip_kubernetes_version(kubernetes_version)
        autoscaler_file_path = "autoscaler.yaml"

        autoscaler_image_tag_override = cluster_config.get("autoscalerImageTagOverride", None)
        autoscaler_image_tag = select_autoscaler_image(kubernetes_version, autoscaler_registry_url, autoscaler_image_tag_override)

        autoscaler_full_config = list(yaml.safe_load_all(get_autoscaler_roles()))
        autoscaler_config = yaml.safe_load(get_autoscaler_config(cluster_id, autoscaler_image_tag, autoscaler_registry_url, aws_region))
        tolerations = set()

        # If there are any taints to patch the autoscaler with in the node group(s) to create,
        # we add them to the autoscaler configuration before updating with another `kubectl apply`
        tolerations.update(Toleration.from_dict(taints))

        # Patch the autoscaler with the tolerations derived from node group(s) taints if any
        if tolerations:
            autoscaler_config["spec"]["template"]["spec"]["tolerations"] = Toleration.to_list(tolerations)
            logging.debug("Autoscaler deployment config: %s" % yaml.safe_dump(autoscaler_config, default_flow_style=False))

        autoscaler_full_config.append(autoscaler_config)
        logging.debug("Autoscaler complete config: %s" % yaml.safe_dump_all(autoscaler_full_config, default_flow_style=False))

        with open(autoscaler_file_path, "w") as f:
            yaml.safe_dump_all(autoscaler_full_config, f, explicit_start=True)

        env = os.environ.copy()
        env["KUBECONFIG"] = kube_config_path
        cmd = ["kubectl", "create", "-f", os.path.abspath(autoscaler_file_path)]
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
  - apiGroups: ["resource.k8s.io"]
    resources: ["deviceclasses", "resourceslices", "resourceclaims"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses", "csinodes", "csidrivers", "csistoragecapacities", "volumeattachments"]
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


def get_autoscaler_config(cluster_id, autoscaler_image_version, autoscaler_registry_url, aws_region):
    # Remove trailing slash if it exists
    autoscaler_registry_url = autoscaler_registry_url.rstrip("/")
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
        - image: %(autoscalerregistryurl)s/autoscaling/cluster-autoscaler:%(autoscalerimageversion)s
          name: cluster-autoscaler
          env:
            - name: AWS_REGION
              value: %(aws_region)s
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
""" % {"autoscalerimageversion": autoscaler_image_version, "clusterid": cluster_id, "autoscalerregistryurl": autoscaler_registry_url, "aws_region": aws_region}
