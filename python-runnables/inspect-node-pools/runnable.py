from dataiku.runnables import Runnable
import dataiku
import json, logging, os
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
        
        print('Inspect Cluster - 1. Start') #Debugger
        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        cluster_id = cluster_def["Name"]

        connection_info = dss_cluster_config.get('config', {}).get('connectionInfo', {})
        
        node_group_id = self.config.get('nodeGroupId', None)
        if node_group_id is None or len(node_group_id) == 0:
            args = ['get', 'nodegroup']
            #args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]

            if _has_not_blank_property(connection_info, 'region'):
                args = args + ['--region', connection_info['region']]
            elif 'AWS_DEFAULT_REGION' is os.environ:
                args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

            args = args + ['-o', 'json']
            print('Start Cluster - 2. Create Cluster') #Debugger

            c = EksctlCommand(args, connection_info)
            node_groups = json.loads(c.run_and_get_output())
            node_group_ids = [node_group['Name'] for node_group in node_groups]
        else:
            node_group_ids = [node_group_id]

        node_groups = []
        for node_group_id in node_group_ids:
            args = ['get', 'nodegroup']
            #args = args + ['-v', '4']
            args = args + ['--cluster', cluster_id]
            args = args + ['--name', node_group_id]

            if _has_not_blank_property(connection_info, 'region'):
                args = args + ['--region', connection_info['region']]
            elif 'AWS_DEFAULT_REGION' is os.environ:
                args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

            args = args + ['-o', 'json']

            c = EksctlCommand(args, connection_info)
            node_group_batch = json.loads(c.run_and_get_output())
            if len(node_group_batch) == 0:
                node_groups.append('<h5>%s</h5><div class="alert alert-error">Unable to get details</div>' % (node_group_id))
                continue
            
            print('Node Group Batch Start')
            print(node_group_batch)
            print('Node Group Batch End')

            node_group = node_group_batch[0]

            node_group_stack_name = node_group['StackName']
            
            args = ['cloudformation', 'describe-stack-resources']
            args = args + ['--stack-name', node_group_stack_name]

            print('Inspect Cluster - 3. aws describe-stack-resources') #Debugger
            
            print('Node Group Start')
            print(node_group)

            print('Node Group End / Stack Start')
            
            print(node_group_stack_name)

            print('Node Group Stack End / Args Start')

            print(args) #Debugger
            print('Node Group Stack End / Args End')

            c = AwsCommand(args, connection_info)
            node_group_dict = json.loads(c.run_and_get_output())
            node_group_resources = [node_group_dict['StackResources'] for node_group_resource in node_group_dict]
            
            # find the auto-scaling-group
            auto_scaling_resource = None
            for r in node_group_resources:
                if r.get('ResourceType', '') == 'AWS::AutoScaling::AutoScalingGroup':
                    auto_scaling_resource = r
                
            if auto_scaling_resource is None:
                node_groups.append('<h5>%s</h5><div class="alert alert-error">Unable to get auto-scaling group</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2)))
                continue

            node_group_auto_scaling_id = auto_scaling_resource['PhysicalResourceId']
            
            args = ['autoscaling', 'describe-auto-scaling-groups']
            args = args + ['--auto-scaling-group-names', node_group_auto_scaling_id]

            c = AwsCommand(args, connection_info)
            auto_scaling_resources = json.loads(c.run_and_get_output()).get('AutoScalingGroups', [])
            
            if len(auto_scaling_resources) == 0:
                node_groups.append('<h5>%s</h5><div class="alert alert-error">Unable to get auto-scaling group\'s resources</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2)))
                continue
                
            auto_scaling_resource = auto_scaling_resources[0]
                
            min_instances = auto_scaling_resource.get('MinSize','')
            cur_instances = len(auto_scaling_resource.get('Instances',[]))
            max_instances = auto_scaling_resource.get('MaxSize','')
            node_groups.append('<h5>%s</h5><pre class="debug">%s</pre><div>Min=%s, current=%s, max=%s</div><pre class="debug">%s</pre>' % (node_group_id, json.dumps(node_group, indent=2), min_instances, cur_instances, max_instances, json.dumps(auto_scaling_resource.get('Instances', []), indent=2)))
        
        return '<div>%s</div>' % ''.join(node_groups)