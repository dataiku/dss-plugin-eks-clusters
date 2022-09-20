import os, sys, json, subprocess, time, logging, yaml

from dataiku.cluster import Cluster

from dku_aws.eksctl_command import EksctlCommand
from dku_kube.kubeconfig import setup_creds_env
from dku_kube.autoscaler import add_autoscaler_if_needed
from dku_kube.gpu_driver import add_gpu_driver_if_needed
from dku_kube.metrics_server import install_metrics_server
from dku_utils.cluster import make_overrides, get_connection_info
from dku_utils.access import _is_none_or_blank
from dku_utils.config_parser import get_security_groups_arg, get_region_arg
from dku_utils.node_pool import get_node_pool_args

class MyCluster(Cluster):
    def __init__(self, cluster_id, cluster_name, config, plugin_config, global_settings):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.config = config
        self.plugin_config = plugin_config
        self.global_settings = global_settings

    def start(self):
        connection_info = get_connection_info(self.config)
        networking_settings = self.config["networkingSettings"]

        has_autoscaling = False
        has_gpu = False
        
        if self.config.get('advanced', False):
            has_autoscaling = self.config.get('clusterAutoScaling')
            has_gpu = self.config.get("advancedGPU")

            # create the cluster directly from a yaml def
            yaml_dict = yaml.safe_load(self.config.get("advancedYaml"))

        else:
            node_pool = self.config.get('nodePool', {})

            has_autoscaling = node_pool.get('numNodesAutoscaling', False)
            has_gpu = node_pool.get("enableGPU", False)

            # build the yaml def. As a first step we run eksctl with
            # as many command line args as possible to get it to produce
            # a good base for the cluster yaml def, then we spice it up
            # according to the settings that don't have a command-line 
            # arg
            args = ['create', 'cluster']
            args = args + ['-v', '3'] # not -v 4 otherwise there is a debug line in the beginning of the output
            args = args + ['--name', self.cluster_id]
            args = args + get_region_arg(connection_info)
            args = args + ['--full-ecr-access']

            subnets = networking_settings.get('subnets', [])
            if networking_settings.get('privateNetworking', False):
                args = args + ['--node-private-networking']
                private_subnets = networking_settings.get('privateSubnets', [])
                if len(private_subnets) > 0:
                    args = args + ['--vpc-private-subnets', ','.join(private_subnets)]
            if len(subnets) > 0:
                args = args + ['--vpc-public-subnets', ','.join(subnets)]

            args += get_security_groups_arg(networking_settings)

            args += get_node_pool_args(node_pool)

            k8s_version = self.config.get("k8sVersion", None)
            if not _is_none_or_blank(k8s_version):
                args = args + ['--version', k8s_version.strip()]
                
            c = EksctlCommand(args + ["--dry-run"], connection_info)
            yaml_spec = c.run_and_get_output()
            logging.info("Got spec:\n%s" % yaml_spec)
            
            yaml_dict = yaml.safe_load(yaml_spec)
            
            if self.config.get('privateCluster', False):
                logging.info("Making the cluster fully-private")
                
                private_cluster = yaml_dict.get('privateCluster', {})
                yaml_dict['privateCluster'] = private_cluster
                private_cluster['enabled'] = True
                if self.config.get('skipEndpointCreation', False):
                    private_cluster['skipEndpointCreation'] = True
                else:
                    private_cluster['skipEndpointCreation'] = False
                    if has_autoscaling:
                        private_cluster["additionalEndpointServices"] = private_cluster.get('additionalEndpointServices', [])
                        if not 'autoscaling' in private_cluster["additionalEndpointServices"]:
                            private_cluster["additionalEndpointServices"].append('autoscaling')
                        
                # clear the vpc.clusterEndpoints 
                yaml_dict['vpc'] = yaml_dict.get('vpc', {})
                yaml_dict['vpc']['clusterEndpoints'] = None
                
                # make sure we have a security group to use as shared security group
                # the issue being that eksctl puts this guy on the private VPC endpoints
                # and if you don't control it, then the DSS VM will have no access to the 
                # endpoints, and eksctl will start failing on calls to EC2
                security_group = self.config.get('sharedSG', '').strip()
                if len(security_group) == 0:
                    raise Exception("A shared SG is needed to guarantee that the control plane will be accessible from the DSS VM")
                yaml_dict['vpc']['sharedNodeSecurityGroup'] = security_group
                                
                
            def add_pre_bootstrap_commands(commands, yaml_dict):
                for node_pool_dict in yaml_dict['managedNodeGroups']:
                    if node_pool_dict.get('preBootstrapCommands') is None:
                        node_pool_dict['preBootstrapCommands'] = []
                    for command in commands.split('\n'):
                        if len(command.strip()) > 0:
                            node_pool_dict['preBootstrapCommands'].append(command)
                
            if node_pool.get('addPreBootstrapCommands', False) and not _is_none_or_blank(node_pool.get("preBootstrapCommands", "")):
                # has to be added in the yaml, there is no command line flag for that
                commands = node_pool.get("preBootstrapCommands", "")
                add_pre_bootstrap_commands(commands, yaml_dict)

        # whatever the setting, make the cluster from the yaml config
        yaml_loc = os.path.join(os.getcwd(), self.cluster_id +'_config.yaml')
        with open(yaml_loc, 'w') as outfile:
            yaml.dump(yaml_dict, outfile, default_flow_style=False)
        logging.info("Final spec\n%s" % yaml.dump(yaml_dict))

        args = ['create', 'cluster']
        args = args + ['-v', '4']
        args = args + ['-f', yaml_loc]

        # we don't add the context to the main config file, to not end up with an oversized config,
        # and because 2 different clusters could be concurrently editing the config file
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        args = args + ['--kubeconfig', kube_config_path]

        # if a previous kubeconfig exists, it will be merged with the current configuration, possibly keeping unwanted configuration
        # deleting it ensures a coherent configuration for the cluster
        if os.path.isfile(kube_config_path):
            os.remove(kube_config_path)

        c = EksctlCommand(args, connection_info)
        if c.run_and_log() != 0:
            raise Exception("Failed to start cluster")

        args = ['get', 'cluster']
        args = args + ['--name', self.cluster_id]
        args = args + get_region_arg(connection_info)
        args = args + ['-o', 'json']

        setup_creds_env(kube_config_path, connection_info, self.config)

        if has_autoscaling:
            logging.info("Nodegroup is autoscaling, ensuring autoscaler")
            add_autoscaler_if_needed(self.cluster_id, kube_config_path)
        if has_gpu:
            logging.info("Nodegroup is GPU-enabled, ensuring NVIDIA GPU Drivers")
            add_gpu_driver_if_needed(self.cluster_id, kube_config_path, connection_info)

        if self.config.get('installMetricsServer'):
            install_metrics_server(kube_config_path)

        c = EksctlCommand(args, connection_info)
        cluster_info = json.loads(c.run_and_get_output())[0]

        with open(kube_config_path, "r") as f:
            kube_config = yaml.safe_load(f)

        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(self.config, kube_config, kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        connection_info = get_connection_info(self.config)

        args = ['delete', 'cluster']
        args = args + ['-v', '4']
        args = args + ['--name', self.cluster_id]
        args = args + get_region_arg(connection_info)
        c = EksctlCommand(args, connection_info)

        if c.run_and_log() != 0:
            raise Exception("Failed to stop cluster")
