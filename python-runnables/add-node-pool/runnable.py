from dataiku.runnables import Runnable
import dataiku
import json, logging
from dku_kube.autoscaler import add_autoscaler_if_needed
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_utils.access import _has_not_blank_property

class MyRunnable(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])

        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        cluster_id = cluster_def["Name"]

        # the cluster is accessible via the kubeconfig
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']

        connection_info = dss_cluster_config.get('config', {}).get('connectionInfo', {})
        
        node_group_id = self.config.get('nodeGroupId', None)
        
        args = ['create', 'nodegroup']
        args = args + ['-v', '4']
        args = args + ['--cluster', cluster_id]
        if node_group_id is not None and len(node_group_id) > 0:
            args = args + ['--name', node_group_id]
        
        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]
            
        if dss_cluster_config['config'].get('useEcr', False):
            args = args + ['--full-ecr-access']
            
        if dss_cluster_config.get('privateNetworking', False):
            args = args + ['--node-private-networking']
            
        security_groups = dss_cluster_config['config'].get('securityGroups', [])
        if len(security_groups) > 0:
            args = args + ['--node-security-groups', ','.join(security_groups)]
            
            
        node_pool = self.config.get('nodePool', {})
        if 'machineType' in node_pool:
            args = args + ['--node-type', node_pool['machineType']]
        if 'diskType' in node_pool:
            args = args + ['--node-volume-type', node_pool['diskType']]
        if 'diskSizeGb' in node_pool and node_pool['diskSizeGb'] > 0:
            args = args + ['--node-volume-size', str(node_pool['diskSizeGb'])]
            
        args = args + ['--nodes', str(node_pool.get('numNodes', 3))]
        if node_pool.get('numNodesAutoscaling', False):
            args = args + ['--asg-access']
            args = args + ['--nodes-min', str(node_pool.get('minNumNodes', 2))]
            args = args + ['--nodes-max', str(node_pool.get('maxNumNodes', 5))]

        c = EksctlCommand(args, connection_info)
        if c.run_and_log() != 0:
            raise Exception("Failed to add nodegroup")
        
        if node_pool.get('numNodesAutoscaling', False):
            logging.info("Nodegroup is autoscaling, ensuring autoscaler")
            add_autoscaler_if_needed(cluster_id, kube_config_path)

        args = ['get', 'nodegroup']
        #args = args + ['-v', '4']
        args = args + ['--cluster', cluster_id]

        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

        args = args + ['-o', 'json']

        c = EksctlCommand(args, connection_info)
        node_groups_str = c.run_and_get_output()
        
        return '<h5>Nodegroup added<h5><pre class="debug">%s</pre>' % node_groups_str
