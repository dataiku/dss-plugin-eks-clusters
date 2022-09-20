from dataiku.runnables import Runnable
import dataiku
import os, json, logging, yaml
from dku_kube.autoscaler import add_autoscaler_if_needed
from dku_kube.gpu_driver import add_gpu_driver_if_needed
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster, get_connection_info
from dku_utils.config_parser import get_security_groups_arg, get_region_arg
from dku_utils.node_pool import get_node_pool_args
from dku_utils.access import _is_none_or_blank

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

        connection_info = get_connection_info(dss_cluster_config.get('config'))
        
        node_group_id = self.config.get('nodeGroupId', None)
        
        # first pass: get the yaml config corresponding to the command line args
        args = ['create', 'nodegroup']
        args = args + ['-v', '3'] # not -v 4 otherwise there is a debug line in the beginning of the output
        args = args + ['--cluster', cluster_id]
        if node_group_id is not None and len(node_group_id) > 0:
            args = args + ['--name', node_group_id]
        
        args = args + get_region_arg(connection_info)
            
        if dss_cluster_config['config'].get('useEcr', False):
            args = args + ['--full-ecr-access']
            
        if dss_cluster_config.get('privateNetworking', False) or self.config.get('privateNetworking', None):
            args = args + ['--node-private-networking']
            
        args += get_security_groups_arg(dss_cluster_config['config'])

        node_pool = self.config.get('nodePool', {})
        args += get_node_pool_args(node_pool)

        c = EksctlCommand(args + ["--dry-run"], connection_info)
        yaml_spec = c.run_and_get_output()
        logging.info("Got spec:\n%s" % yaml_spec)

        yaml_dict = yaml.safe_load(yaml_spec)
        
        # second step: add the stuff that has no equivalent command line arg, and run the 
        # eksctl command on the yaml config
        if not _is_none_or_blank(node_pool.get("preBootstrapCommands", "")):
            # has to be added in the yaml, there is no command line flag for that
            commands = node_pool.get("preBootstrapCommands", "")
            for node_pool_dict in yaml_dict['managedNodeGroups']:
                if node_pool_dict.get('preBootstrapCommands') is None:
                    node_pool_dict['preBootstrapCommands'] = []
                for command in commands.split('\n'):
                    if len(command.strip()) > 0:
                        node_pool_dict['preBootstrapCommands'].append(command)
        
        yaml_loc = os.path.join(os.getcwd(), cluster_id +'_config.yaml')
        with open(yaml_loc, 'w') as outfile:
            yaml.dump(yaml_dict, outfile, default_flow_style=False)
        logging.info("Final spec\n%s" % yaml.dump(yaml_dict))

        args = ['create', 'nodegroup']
        args = args + ['-v', '4']
        args = args + ['-f', yaml_loc]

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

        args = args + get_region_arg(connection_info)

        args = args + ['-o', 'json']

        c = EksctlCommand(args, connection_info)
        node_groups_str = c.run_and_get_output()
        
        return '<h5>Nodegroup added<h5><pre class="debug">%s</pre>' % node_groups_str
