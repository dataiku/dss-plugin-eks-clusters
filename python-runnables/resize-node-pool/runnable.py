from dataiku.runnables import Runnable
import dataiku
import json, logging
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster

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

        connection_info = {'config':dss_cluster_config.get('config', {}).get('connectionInfo', {}), 'pluginConfig':dss_cluster_config.get('pluginConfig', {}).get('connectionInfo', {})}
        
        node_group_id = self.config.get('nodeGroupId', None)
        if node_group_id is None or len(node_group_id) == 0:
            args = ['get', 'nodegroup']
            #args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]

            if 'region' in connection_info.get('config', {}):
                args = args + ['--region', connection_info['config']['region']]
            elif 'AWS_DEFAULT_REGION' is os.environ:
                args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

            args = args + ['-o', 'json']

            c = EksctlCommand(args, connection_info)
            node_groups = json.loads(c.run_and_get_output())
            node_group_ids = [node_group['Name'] for node_group in node_groups]
            if len(node_group_ids) != 1:
                raise Exception("Cluster has %s node groups, cannot resize. Specify a node group explicitely among %s" % (len(node_group_ids), json.dumps(node_group_ids)))
            node_group_id = node_group_ids[0]

        args = ['get', 'nodegroup']
        #args = args + ['-v', '4']
        args = args + ['--cluster', cluster_id]
        args = args + ['--name', node_group_id]

        if 'region' in connection_info.get('config', {}):
            args = args + ['--region', connection_info['config']['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

        args = args + ['-o', 'json']

        c = EksctlCommand(args, connection_info)
        node_group_batch = json.loads(c.run_and_get_output())
        if len(node_group_batch) == 0:
            raise Exception("Unable to retrieve info of node group %s" % node_group_id)

        node_group = node_group_batch[0]
            
        desired_count = self.config['numNodes']
        logging.info("Resize to %s" % desired_count)
        if desired_count == 0:
            args = ['delete', 'nodegroup']
            args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]
            args = args + ['--name', node_group_id]

            if 'region' in connection_info.get('config', {}):
                args = args + ['--region', connection_info['config']['region']]
            elif 'AWS_DEFAULT_REGION' is os.environ:
                args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

            c = EksctlCommand(args, connection_info)
            c.run_and_log()
            logging.info("Cluster node group deleted")
            return '<div>Deleted</div><pre class="debug">%s</pre>' % node_group_id
        else:
            args = ['scale', 'nodegroup']
            args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]
            args = args + ['--name', node_group_id]
            args = args + ['--nodes', str(desired_count)]

            if 'region' in connection_info.get('config', {}):
                args = args + ['--region', connection_info['config']['region']]
            elif 'AWS_DEFAULT_REGION' is os.environ:
                args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

            c = EksctlCommand(args, connection_info)
            c.run_and_log()
            logging.info("Cluster node group resized")
            return '<div>Resized</div><pre class="debug">%s</pre>' % node_group_id
        
        
        