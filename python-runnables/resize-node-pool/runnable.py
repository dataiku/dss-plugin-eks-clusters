from dataiku.runnables import Runnable
import dataiku
import os, json, logging
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster, get_connection_info
from dku_utils.config_parser import get_region_arg

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

        connection_info = get_connection_info(dss_cluster_config.get('config'))
        
        node_group_id = self.config.get('nodeGroupId', None)
        if node_group_id is None or len(node_group_id) == 0:
            args = ['get', 'nodegroup']
            #args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]
            args = args + get_region_arg(connection_info)
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
        args = args + get_region_arg(connection_info)
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
            args = args + get_region_arg(connection_info)

            c = EksctlCommand(args, connection_info)
            rv, out, err = c.run_and_get()
            if rv == 0:
                logging.info("Cluster node group deleted")
                return '<div>Deleted</div><pre class="debug">%s</pre>' % node_group_id
            else:
                logging.info("Cluster node group failed to delete")
                return '<div>Failed to delete the node group</div><pre class="debug">%s</pre>' % (err)
                
        else:
            args = ['scale', 'nodegroup']
            args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]
            args = args + ['--name', node_group_id]
            args = args + ['--nodes', str(desired_count)]
            desired_min_count = self.config.get('minNumNodes', -1)
            desired_max_count = self.config.get('maxNumNodes', -1)
            if desired_min_count > 0:
                args = args + ['--nodes-min', str(desired_min_count)]
            if desired_max_count > 0:
                args = args + ['--nodes-max', str(desired_max_count)]
            args = args + get_region_arg(connection_info)

            c = EksctlCommand(args, connection_info)
            rv, out, err = c.run_and_get()
            if rv == 0:
                logging.info("Cluster node group resized")
                return '<div>Resized</div><pre class="debug">%s</pre>' % node_group_id
            else:
                logging.info("Cluster node group failed to resize")
                return '<div>Failed to resize the node group</div><pre class="debug">%s</pre>' % (err)
        
        
        
