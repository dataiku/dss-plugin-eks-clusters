from dataiku.runnables import Runnable
import dataiku
import json, logging, os
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

        # There's a bug in `eksctl` where the `StackName` doesn't appear in the output
        # if `get nodegroup` is called with a single node group name and that node
        # group is "managed". So, always get all node groups, even if only one is
        # specified in the params and even though we don't use the `StackName` anymore.
        args = ['get', 'nodegroup']
        args = args + ['--cluster', cluster_id]
        args = args + get_region_arg(connection_info)
        args = args + ['-o', 'json']

        c = EksctlCommand(args, connection_info)
        node_groups = json.loads(c.run_and_get_output())

        if node_group_id and len(node_group_id) != 0:
            node_groups = list(filter(lambda node_group: node_group.get('Name') == node_group_id, node_groups))

            if len(node_groups) == 0:
                return '<div><h5>%s</h5><div class="alert alert-error">Unable to get details</div></div>' % (node_group_id)

        node_group_outputs = []
        for node_group in node_groups:
            node_group_id = node_group.get('Name')
            node_group_auto_scaling_id = node_group.get('AutoScalingGroupName')

            if node_group_auto_scaling_id is None:
                node_group_outputs.append('<h5>%s</h5><div class="alert alert-error">Unable to get auto-scaling group</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2)))
                continue

            args = ['autoscaling', 'describe-auto-scaling-groups']
            args = args + ['--auto-scaling-group-names', node_group_auto_scaling_id]

            c = AwsCommand(args, connection_info)
            auto_scaling_resources = json.loads(c.run_and_get_output()).get('AutoScalingGroups', [])
            
            if len(auto_scaling_resources) == 0:
                node_group_outputs.append('<h5>%s</h5><div class="alert alert-error">Unable to get auto-scaling group\'s resources</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2)))
                continue
                
            auto_scaling_resource = auto_scaling_resources[0]
                
            min_instances = auto_scaling_resource.get('MinSize','')
            cur_instances = len(auto_scaling_resource.get('Instances',[]))
            max_instances = auto_scaling_resource.get('MaxSize','')
            node_group_outputs.append('<h5>%s</h5><pre class="debug">%s</pre><div>Min=%s, current=%s, max=%s</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2), min_instances, cur_instances, max_instances, json.dumps(auto_scaling_resource.get('Instances', []), indent=2)))
        
        return '<div>%s</div>' % ''.join(node_group_outputs)