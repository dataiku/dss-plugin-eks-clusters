import json, re
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException
from dku_aws.eksctl_command import EksctlCommand
from dku_utils.cluster import get_connection_info

def get_kubectl_version():
    cmd = ['kubectl', 'version', '--client', '-o', 'json']
    out, err = run_with_timeout(cmd)
    return json.loads(out)['clientVersion']

def kubectl_version_to_string(kubectl_version):
    """
    Writes as a string the Kubernetes version coming from outcome of `kubectl version` command
    """
    major = str(kubectl_version['major']) if 'major' in kubectl_version else ''
    minor = str(kubectl_version['minor']) if 'minor' in kubectl_version else ''
    return major + '.' + minor

def get_kubectl_version_int(kubectl_version):
    """
    Extracts the integers representing the major version and the minor version coming from outcome
    of `kubectl version` command
    """
    # the kubectl version downloaded from Amazon website has a minor version finishing by '+'
    # keeping only the first numeric sequence for the minor version
    if 'major' not in kubectl_version or 'minor' not in kubectl_version:
        raise Exception("Kubectl version found on the machine: %s. It is not correctly formatted" % kubectl_version_to_string(kubectl_version))
    regex_minor_int = re.compile("^[^0-9]*([0-9]+)([^0-9].*$|$)")
    search_results_minor_int = re.search(regex_minor_int, kubectl_version['minor'])
    if not search_results_minor_int or not search_results_minor_int.groups():
        raise Exception("Kubectl version found on the machine: %s. It was not possible to parse" % kubectl_version_to_string(kubectl_version))
    minor_int = int(search_results_minor_int.groups()[0])
    return int(kubectl_version['major']), minor_int

def strip_kubernetes_version(k8s_version_input):
    """
    Removes any additional characters from the Kubernetes version specified in the cluster creation form
    """
    regex_k8s_version = re.compile("^[^0-9]*([0-9]+\.?[0-9]+)([^0-9].*$|$)")
    search_results_k8s_version = re.search(regex_k8s_version, k8s_version_input)
    if not search_results_k8s_version or not search_results_k8s_version.groups():
        raise Exception("Kubectl version specified: %s. No valid Kubernetes version found", k8s_version_input)
    return search_results_k8s_version.groups()[0]

def get_authenticator_version():
    cmd = ['aws-iam-authenticator', 'version', '-o', 'json']
    out, err = run_with_timeout(cmd)
    return json.loads(out)['Version'].lstrip('v')

def kubectl_should_use_beta_apiVersion(kubectl_version):
    version_int = get_kubectl_version_int(kubectl_version)
    major = version_int[0]
    minor = version_int[1]
    return major > 1 or (major == 1 and minor > 23)  # v1alpha1 was deprecated in 1.24

def check_versions():
    kubectl_version = get_kubectl_version()
    authenticator_version = get_authenticator_version()
    if kubectl_should_use_beta_apiVersion(kubectl_version) and authenticator_version < '0.5.4':
        raise Exception('Found kubectl %s and aws-iam-authenticator %s, which are incompatible. Please upgrade aws-iam-authenticator.' 
                        % (kubectl_version['major']+'.'+(kubectl_version['minor']), authenticator_version))
