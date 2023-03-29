from dataiku.runnables import Runnable
import os, re
import dku_utils.tools_version
from dku_utils.cluster import get_cluster_from_dss_cluster

class CheckKubeconfig(Runnable):

    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        result = ''

        cluster_data, dss_cluster_settings, _ = get_cluster_from_dss_cluster(self.config['clusterId'])
        # the cluster is accessible via the kubeconfig
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides'].get('kubeConfigPath', None)

        if kube_config_path is None or not os.path.isfile(kube_config_path):
            return '<div>Kubeconfig file not found, cluster was probably never started, nothing to do.</div>'
        
        try:
            kubectl_version = dku_utils.tools_version.get_kubectl_version()
            result += '<div>Found kubectl version: %s.%s</div>' % (kubectl_version['major'], kubectl_version['minor'])
            should_use_beta_api = dku_utils.tools_version.kubectl_should_use_beta_apiVersion(kubectl_version)

            aws_iam_authenticator_version = dku_utils.tools_version.get_authenticator_version()
            result += '<div>Found aws-iam-authenticator version: %s</div>' % aws_iam_authenticator_version
            # aws-iam-authenticator defaults to beta since 0.5.4 : https://github.com/kubernetes-sigs/aws-iam-authenticator/commit/0221afb8e2a5d14a20a93473edc4c2aa7676ce95
            if should_use_beta_api and aws_iam_authenticator_version < '0.5.4':
                return result + '<div class="alert alert-error"><div>kubectl and aws-iam-authenticator versions are incompatible, please upgrade aws-iam-authenticator.</div></div>'
        except Exception as e:
            return '<div class="alert alert-error">%s</div>' % str(e)
        

        result += '<div>Inspecting config at: %s</div>' % kube_config_path
        if self.update_kube_config_file(kube_config_path, should_use_beta_api):
            result += '<div>Updated apiVersion from v1alpha1 to v1beta1.</div>'
        else:
            result += '<div>Everything is correct, nothing to do.</div>'

        return result
    
    def update_kube_config_file(self, kube_config_path, should_use_beta_api):
        with open(kube_config_path, 'r+') as f:
            kube_config_yaml = f.read()
            if should_use_beta_api and re.search('[ \t]*apiVersion[ \t]*:[ \t]*client\.authentication\.k8s\.io/v1alpha1', kube_config_yaml):
                kube_config_yaml = re.sub('apiVersion[ \t]*:[ \t]*client\.authentication\.k8s\.io/v1alpha1', 'apiVersion: client.authentication.k8s.io/v1beta1', kube_config_yaml)
                f.seek(0)
                f.write(kube_config_yaml)
                return True
            else:
                return False
