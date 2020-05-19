import os, sys, json, subprocess, time, logging, yaml

import boto3

from dataiku.cluster import Cluster

from dku_aws.eksctl_command import EksctlCommand
from dku_kube.kubeconfig import merge_or_write_config, add_authenticator_env
from dku_kube.autoscaler import add_autoscaler_if_needed
from dku_utils.cluster import make_overrides
from dku_utils.access import _has_not_blank_property, _is_none_or_blank

class MyCluster(Cluster):
    def __init__(self, cluster_id, cluster_name, config, plugin_config, global_settings):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.config = config
        self.plugin_config = plugin_config
        self.global_settings = global_settings
        
    def start(self):
        connection_info = self.config.get('connectionInfo', {})
        networking_settings = self.config["networkingSettings"]
        
        args = ['create', 'cluster']
        args = args + ['-v', '4']
        args = args + ['--name', self.cluster_id]
        
        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]
            
        args = args + ['--full-ecr-access']
            
        subnets = networking_settings.get('subnets', [])
        if networking_settings.get('privateNetworking', False):
            args = args + ['--node-private-networking']
            private_subnets = networking_settings.get('privateSubnets', [])
            if len(private_subnets) > 0:
                args = args + ['--vpc-private-subnets', ','.join(private_subnets)]
        if len(subnets) > 0:
            args = args + ['--vpc-public-subnets', ','.join(subnets)]
            
        security_groups = networking_settings.get('securityGroups', [])
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

        # we don't add the context to the main config file, to not end up with an oversized config,
        # and because 2 different clusters could be concurrently editing the config file
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        args = args + ['--kubeconfig', kube_config_path]
        
        k8s_version = self.config.get("k8sVersion", None)
        if not _is_none_or_blank(k8s_version):
            args = args + ['--version', k8s_version.strip()]

        c = EksctlCommand(args, connection_info)
        if c.run_and_log() != 0:
            raise Exception("Failed to start cluster")
        
        args = ['get', 'cluster']
        args = args + ['--name', self.cluster_id]
        
        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]
        args = args + ['-o', 'json']
        
        if _has_not_blank_property(connection_info, 'accessKey') and _has_not_blank_property(connection_info, 'secretKey'):
            creds_in_env = {'AWS_ACCESS_KEY_ID':connection_info['accessKey'], 'AWS_SECRET_ACCESS_KEY':connection_info['secretKey']}
            add_authenticator_env(kube_config_path, creds_in_env)
        
        if node_pool.get('numNodesAutoscaling', False):
            logging.info("Nodegroup is autoscaling, ensuring autoscaler")
            add_autoscaler_if_needed(self.cluster_id, kube_config_path)

        c = EksctlCommand(args, connection_info)
        cluster_info = json.loads(c.run_and_get_output())[0]

        if networking_settings.get('privateNetworking', False):
            self.make_private(cluster_info['ResourcesVpcConfig']['SecurityGroupIds'][0])
        
        with open(kube_config_path, "r") as f:
            kube_config = yaml.safe_load(f)
        
        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(self.config, kube_config, kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        connection_info = self.config.get('connectionInfo', {})
        networking_settings = self.config["networkingSettings"]
        
        args = ['delete', 'cluster']
        args = args + ['-v', '4']
        args = args + ['--name', self.cluster_id]

        if _has_not_blank_property(connection_info, 'region'):
            region = connection_info['region']
        elif 'AWS_DEFAULT_REGION' is os.environ:
            region = os.environ['AWS_DEFAULT_REGION']
            
        args = args + ['--region', region]
        
        if networking_settings.get('privateNetworking', False):
            dss_sg = networking_settings.get('dssSecurityGroup', '')

            if dss_sg:
                pid = os.fork()
                
                if pid == 0:
                    time.sleep(180)
                    eks = boto3.client(
                        'eks',
                        aws_access_key_id=connection_info['accessKey'],
                        aws_secret_access_key=connection_info['secretKey'],
                        region_name=region
                    )
                    response = eks.describe_cluster(
                        name=self.cluster_id
                    )

                    cluster_sg = response['cluster']['resourcesVpcConfig']['securityGroupIds'][0]

                    ec2 = boto3.client(
                        'ec2',
                        aws_access_key_id=connection_info['accessKey'],
                        aws_secret_access_key=connection_info['secretKey'],
                        region_name=region
                    )

                    response = ec2.revoke_security_group_egress(
                        GroupId=dss_sg,
                        IpPermissions=[
                            {
                                'FromPort': 443,
                                'IpProtocol': 'tcp',
                                'ToPort': 443,
                                'UserIdGroupPairs': [
                                    {
                                        'Description': 'Allow outbound from DSS SG to private cluster endpoint SG',
                                        'GroupId': cluster_sg
                                    }
                                ]
                            }
                        ]
                    )

                    response = ec2.revoke_security_group_ingress(
                        GroupId=cluster_sg,
                        IpPermissions=[
                            {
                                'FromPort': 443,
                                'IpProtocol': 'tcp',
                                'ToPort': 443,
                                'UserIdGroupPairs': [
                                    {
                                        'Description': 'Allow inbound to private cluster endpoint SG from DSS SG',
                                        'GroupId': dss_sg
                                    }
                                ]
                            }
                        ]
                    )
        
        c = EksctlCommand(args, connection_info)

        if c.run_and_log() != 0:
            raise Exception("Failed to stop cluster") 

    def make_private(self, cluster_sg):
        networking_settings = self.config["networkingSettings"]
        connection_info = self.config.get('connectionInfo', {})
        
        if _has_not_blank_property(connection_info, 'region'):
            region = connection_info['region']
        elif 'AWS_DEFAULT_REGION' is os.environ:
            region = os.environ['AWS_DEFAULT_REGION']
            
        client = boto3.client(
            'ec2',
            aws_access_key_id=connection_info['accessKey'],
            aws_secret_access_key=connection_info['secretKey'],
            region_name=region
        )
        args = ['utils', 'update-cluster-endpoints', '--cluster', self.cluster_id, '--private-access=true', '--public-access=false', '--approve']
        
        c = EksctlCommand(args, connection_info)
        if c.run_and_log() != 0:
            raise Exception("Failed to update to private cluster")
            
        dss_sg = networking_settings.get('dssSecurityGroup', '')
        
        if dss_sg:
            response = client.authorize_security_group_egress(
                GroupId=dss_sg,
                IpPermissions=[
                    {
                        'FromPort': 443,
                        'IpProtocol': 'tcp',
                        'ToPort': 443,
                        'UserIdGroupPairs': [
                            {
                                'Description': 'Allow outbound from DSS SG to private cluster endpoint SG',
                                'GroupId': cluster_sg
                            }
                        ]
                    }
                ]
            )
            
            response = client.authorize_security_group_ingress(
                GroupId=cluster_sg,
                IpPermissions=[
                    {
                        'FromPort': 443,
                        'IpProtocol': 'tcp',
                        'ToPort': 443,
                        'UserIdGroupPairs': [
                            {
                                'Description': 'Allow inbound to private cluster endpoint SG from DSS SG',
                                'GroupId': dss_sg
                            }
                        ]
                    }
                ]
            )
        