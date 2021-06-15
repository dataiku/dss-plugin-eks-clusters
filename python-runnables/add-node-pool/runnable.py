from dataiku.runnables import Runnable
import dataiku
import os, json, logging
from dku_kube.autoscaler import add_autoscaler_if_needed
from dku_kube.gpu_driver import add_gpu_driver_if_needed
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_utils.access import _has_not_blank_property
from dku_aws.boto3_command import get_dss_instance_variables

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

        spot_pool_bln = self.config.get('spotPool', None)

        node_labels = self.config.get('nodeLabels', None)
        
        networking_settings = dss_cluster_config.get('config', {}).get('networkingSettings', {})

        security_groups = networking_settings.get('securityGroups', [])
        
        availability_zone = get_dss_instance_variables()['availability_zone'] 
    
    
        args = ['create', 'nodegroup']
        args = args + ['-v', '4']
        args = args + ['--cluster', cluster_id]

        # Pickup if this a Spot Instance and if so instatiate as Managed Spot 
        if spot_pool_bln is not None and spot_pool_bln:
            args = args + ['--managed']
            args = args + ['--spot']
            args = args + ['--node-zones', availability_zone]

        if node_group_id is not None and len(node_group_id) > 0:
            args = args + ['--name', node_group_id]

        if node_labels is not None and len(node_labels) > 0:
            args = args + ['--node-labels', node_labels]            
        
        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

        # This does not appear to be in the configuration at this point, doing nothing    
        if dss_cluster_config['config'].get('useEcr', False):
            args = args + ['--full-ecr-access']


        if networking_settings.get('privateNetworking', False) or self.config.get('privateNetworking', None):
            args = args + ['--node-private-networking']
            
        
        if len(security_groups) > 0:
            args = args + ['--node-security-groups', ','.join(security_groups)]
            
            
        node_pool = self.config.get('nodePool', {})
        
        print(node_pool[])

        instance_types = ','.join(node_pool['machineType'].itervalues())

        if 'machineType' in node_pool:
            args = args + ['--instance-types', instance_types]
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
            
        if node_pool.get('enableGPU', False):
            logging.info("Nodegroup is GPU-enabled, ensuring NVIDIA GPU Drivers")
            add_gpu_driver_if_needed(self.config['clusterId'], kube_config_path, connection_info)

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
