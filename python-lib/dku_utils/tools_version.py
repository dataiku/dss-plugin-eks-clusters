import json
import re
from dku_kube.kubectl_command import run_with_timeout

KUBERNETES_VERSION_RE = re.compile(r"^([0-9]+)\.([0-9]+)(?:\.([0-9]+))?$")


def get_kubectl_version():
    cmd = ["kubectl", "version", "--client", "-o", "json"]
    out, err = run_with_timeout(cmd, timeout=30)
    return json.loads(out)["clientVersion"]


def kubectl_version_to_string(kubectl_version):
    """
    Writes as a string the Kubernetes version coming from outcome of `kubectl version` command
    """
    major = str(kubectl_version["major"]) if "major" in kubectl_version else ""
    minor = str(kubectl_version["minor"]) if "minor" in kubectl_version else ""
    return major + "." + minor


def get_kubectl_version_int(kubectl_version):
    """
    Extracts the integers representing the major version and the minor version coming from outcome
    of `kubectl version` command
    """
    if "major" not in kubectl_version or "minor" not in kubectl_version:
        raise Exception("Kubectl version found on the machine: %s. It is not correctly formatted" % kubectl_version_to_string(kubectl_version))

    # The kubectl version downloaded from Amazon can have a minor version ending with '+';
    # normalize it before using the generic Kubernetes major/minor parser.
    normalized_version = strip_kubernetes_version(kubectl_version_to_string(kubectl_version))
    try:
        major_int, minor_int, _ = parse_kubernetes_version(normalized_version)
    except Exception:
        raise Exception("Kubectl version found on the machine: %s. It was not possible to parse" % kubectl_version_to_string(kubectl_version))
    return major_int, minor_int


def strip_kubernetes_version(k8s_version_input):
    """
    Removes any additional characters from the Kubernetes version specified in the cluster creation form
    """
    regex_k8s_version = re.compile(r"^[^0-9]*([0-9]+\.?[0-9]+)([^0-9].*$|$)")
    search_results_k8s_version = re.search(regex_k8s_version, k8s_version_input)
    if not search_results_k8s_version or not search_results_k8s_version.groups():
        raise Exception("Kubectl version specified: %s. No valid Kubernetes version found", k8s_version_input)
    return search_results_k8s_version.groups()[0]


def parse_kubernetes_version(version):
    """
    Parses a Kubernetes version string and returns its major, minor, and major.minor string.
    EKS cluster versions are usually major.minor, but a patch version is accepted too.
    """
    match = KUBERNETES_VERSION_RE.match(version)
    if match is None:
        raise Exception("Kubernetes version specified: %s. No valid Kubernetes major/minor version found" % version)
    major = int(match.group(1))
    minor = int(match.group(2))
    return major, minor, "%s.%s" % (major, minor)


def get_authenticator_version():
    cmd = ["aws-iam-authenticator", "version", "-o", "json"]
    out, err = run_with_timeout(cmd, timeout=30)
    return json.loads(out)["Version"].lstrip("v")


def kubectl_should_use_beta_apiVersion(kubectl_version):
    version_int = get_kubectl_version_int(kubectl_version)
    major = version_int[0]
    minor = version_int[1]
    return major > 1 or (major == 1 and minor > 23)  # v1alpha1 was deprecated in 1.24


def check_versions():
    kubectl_version = get_kubectl_version()
    authenticator_version = get_authenticator_version()
    if kubectl_should_use_beta_apiVersion(kubectl_version) and authenticator_version < "0.5.4":
        raise Exception(
            "Found kubectl %s and aws-iam-authenticator %s, which are incompatible. Please upgrade aws-iam-authenticator."
            % (kubectl_version["major"] + "." + (kubectl_version["minor"]), authenticator_version)
        )
