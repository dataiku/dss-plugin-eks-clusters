import json
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException

def get_kubectl_version():
    cmd = ['kubectl', 'version', '--client', '-o', 'json']
    out, err = run_with_timeout(cmd)
    return json.loads(out)['clientVersion']

def get_authenticator_version():
    cmd = ['aws-iam-authenticator', 'version', '-o', 'json']
    out, err = run_with_timeout(cmd)
    return json.loads(out)['Version'].lstrip('v')

def kubectl_should_use_beta_apiVersion(kubectl_version):
    return int(kubectl_version['major']) > 1 or (int(kubectl_version['major']) == 1 and int(kubectl_version['minor']) > 23)  # v1alpha1 was deprecated in 1.24

def check_versions():
    kubectl_version = get_kubectl_version()
    authenticator_version = get_authenticator_version()
    if kubectl_should_use_beta_apiVersion(kubectl_version) and authenticator_version < '0.5.4':
        raise Exception('Found kubectl %s and aws-iam-authenticator %s, which are incompatible. Please upgrade aws-iam-authenticator.' 
                        % (kubectl_version['major']+'.'+(kubectl_version['minor']), authenticator_version))
