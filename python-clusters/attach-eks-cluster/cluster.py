import os, sys, json, subprocess, time, logging, yaml

from dataiku.cluster import Cluster

from dku_aws.eksctl_command import EksctlCommand
from dku_kube.kubeconfig import setup_creds_env
from dku_utils.cluster import make_overrides, get_connection_info
from dku_utils.config_parser import get_region_arg

class MyCluster(Cluster):
    def __init__(self, cluster_id, cluster_name, config, plugin_config, global_settings):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.config = config
        self.plugin_config = plugin_config
        self.global_settings = global_settings

    def start(self):
        cluster_id = self.config['clusterId']
        
        # retrieve the cluster info from EKS
        # this will fail if the cluster doesn't exist, but the API message is enough

        connection_info = get_connection_info(self.config)
            
        args = ['get', 'cluster']
        args = args + ['--name', cluster_id]

        args = args + get_region_arg(connection_info)
        args = args + ['-o', 'json']

        c = EksctlCommand(args, connection_info)
        cluster_info = json.loads(c.run_and_get_output())[0]

        kube_config_str = """
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: %s
    server: %s
  name: cluster-__CLUSTER_ID__
contexts:
- context:
    cluster: cluster-__CLUSTER_ID__
    user: user-__CLUSTER_ID__
  name: context-__CLUSTER_ID__
current-context: context-__CLUSTER_ID__
kind: Config
preferences: {}
users:
- name: user-__CLUSTER_ID__
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1alpha1
      args:
      - token
      - -i
      - %s
      command: aws-iam-authenticator
      env: null
        """ % (cluster_info['CertificateAuthority']['Data'], cluster_info['Endpoint'], cluster_id)
        kube_config_str = kube_config_str.replace("__CLUSTER_ID__", cluster_id) # cluster_id is as good as anything, since this kubeconfig won't be merged into another one

        # build the config file for kubectl
        # we don't add the context to the main config file, to not end up with an oversized config,
        # and because 2 different clusters could be concurrently editing the config file
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        with open(kube_config_path, 'w') as f:
            f.write(kube_config_str)

        setup_creds_env(kube_config_path, connection_info, self.config)

        kube_config = yaml.safe_load(kube_config_str)

        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(self.config, kube_config, kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        pass
