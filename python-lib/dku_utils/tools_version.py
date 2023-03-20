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
    return int(kubectl_version['major']) > 1 or int(kubectl_version['minor']) > 23  # v1alpha1 was deprecated in 1.24
