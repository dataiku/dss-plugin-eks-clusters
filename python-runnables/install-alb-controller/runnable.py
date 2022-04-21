from dataiku.runnables import Runnable
import dataiku
import json, logging, os, re, tempfile, time
import requests 
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster, get_cluster_generic_property, set_cluster_generic_property, get_connection_info
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException
from dku_utils.access import _is_none_or_blank
from dku_utils.config_parser import get_region_arg

def make_html(command_outputs):
    divs = []
    for command_output in command_outputs:
        cmd_html = '<div>Run: %s</div>' % json.dumps(command_output[0])
        rv_html = '<div>Returned %s</div>' % command_output[1]
        out_html = '<div class="alert alert-info"><div>Output</div><pre class="debug" style="max-width: 100%%; max-height: 100%%;">%s</pre></div>' % command_output[2]
        err_html = '<div class="alert alert-danger"><div>Error</div><pre class="debug" style="max-width: 100%%; max-height: 100%%;">%s</pre></div>' % command_output[3]
        divs.append(cmd_html)
        divs.append(rv_html)
        divs.append(out_html)
        if command_output[1] != 0 and not _is_none_or_blank(command_output[3]):
            divs.append(err_html)
    return '\n'.join(divs).decode('utf8')

class InstallAlb(Runnable):
    """
    Installs a ALB ingress controller as described in https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html
    """
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config

    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])

        if get_cluster_generic_property(dss_cluster_settings, 'alb-ingress.controller', 'false') == 'true':
            raise Exception("ALB controller already installed, remove first")

        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        cluster_id = cluster_def["Name"]
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']
        connection_info = get_connection_info(dss_cluster_config.get('config'))
        
        env = os.environ.copy()
        env['KUBECONFIG'] = kube_config_path

        command_outputs = []
        keep_going = True
        
        # setup iam stuff in eksctl
        args = ['utils', 'associate-iam-oidc-provider', '--approve']
        #args = args + ['-v', '4']
        args = args + ['--cluster', cluster_id]
        args = args + get_region_arg(connection_info)

        c = EksctlCommand(args, connection_info)
        command_outputs.append(c.run())
        if command_outputs[-1][1] != 0:
            return make_html(command_outputs)
        
        # checking if we need to create the policy
        policy_name = self.config.get('policyName', 'ALBIngressControllerIAMPolicy')
        
        args = ['iam', 'list-policies']
        args = args + get_region_arg(connection_info)

        c = AwsCommand(args, connection_info)
        command_outputs.append(c.run())
        if command_outputs[-1][1] != 0:
            return make_html(command_outputs)
        
        policy_arn = None
        for policy in json.loads(command_outputs[-1][2])['Policies']:
            if policy.get('PolicyName', None) == policy_name:
                policy_arn = policy.get('Arn', None)

        if policy_arn is None:
            if not self.config.get("createPolicy", False):
                raise Exception("Policy %s doesn't exist and the macro isn't allowed to create it" % policy_name)
            # create the policy
            policy_document_url = 'https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.8/docs/examples/iam-policy.json'
            policy_document = requests.get(policy_document_url).text
            with open("policy.json", "w") as p:
                p.write(policy_document)
            
            args = ['iam', 'create-policy']
            args = args + ['--policy-name', policy_name]
            args = args + ['--policy-document', 'file://policy.json']
            args = args + get_region_arg(connection_info)

            c = AwsCommand(args, connection_info)
            command_outputs.append(c.run())
            if command_outputs[-1][1] != 0:
                return make_html(command_outputs)
            
            policy_arn = json.loads(command_outputs[-1][2])['Policy'].get('Arn', None)

        # create the role on the cluster
        cmd = ['kubectl', 'apply', '-f', 'https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.4/docs/examples/rbac-role.yaml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=100)
            command_outputs.append((cmd, 0, out, err))
        except KubeCommandException as e:
            command_outputs.append((cmd, e.rv, e.out, e.err))
            keep_going = False

        if not keep_going:
            return make_html(command_outputs)

        # attach the role to the policy
        
        args = ['create', 'iamserviceaccount', '--override-existing-serviceaccounts', '--approve']
        #args = args + ['-v', '4']
        args = args + ['--name', 'alb-ingress-controller'] # that's the name in the rbac-role.yaml
        args = args + ['--namespace', 'kube-system'] # that's the name in the rbac-role.yaml
        args = args + ['--cluster', cluster_id]
        args = args + ['--attach-policy-arn', policy_arn]
        args = args + get_region_arg(connection_info)

        c = EksctlCommand(args, connection_info)
        command_outputs.append(c.run())
        if command_outputs[-1][1] != 0:
            return make_html(command_outputs)

        r = requests.get('https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.4/docs/examples/alb-ingress-controller.yaml')
        service_data = r.content
        cluster_flag_pattern = '#.*cluster\\-name=.*'
        cluster_flag_replacement = '- --cluster-name=%s' % cluster_id
        service_data = re.sub(cluster_flag_pattern, cluster_flag_replacement, service_data)
        
        print(service_data)
        with open('./alb-ingress-controller.yaml', 'w') as f:
            f.write(service_data)
            
        cmd = ['kubectl', 'apply', '-f', './alb-ingress-controller.yaml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=100)
            command_outputs.append((cmd, 0, out, err))
        except KubeCommandException as e:
            command_outputs.append((cmd, e.rv, e.out, e.err))
            keep_going = False

        if not keep_going:
            return make_html(command_outputs)

        if self.config.get("tagSubnets", False):
            networking_settings = dss_cluster_config.get('config', {}).get('networkingSettings', {})
            subnets = networking_settings.get('subnets', [])
            if networking_settings.get('privateNetworking', False):
                private_subnets = dss_cluster_config.get('config', {}).get('networkingSettings', {}).get('privateSubnets', [])
            else:
                private_subnets = []
                
            def add_tags(resources, tag, connection_info, command_outputs):
                args = ['ec2', 'create-tags']
                args = args + get_region_arg(connection_info)
                args = args + ["--resources"] + resources
                args = args + ["--tags", tag]

                c = AwsCommand(args, connection_info)
                command_outputs.append(c.run())
                if command_outputs[-1][1] != 0:
                    return make_html(command_outputs)
            
            if len(subnets) > 0:
                add_tags(subnets, 'Key=kubernetes.io/role/elb,Value=1', connection_info, command_outputs)
            if len(private_subnets) > 0:
                add_tags(private_subnets, 'Key=kubernetes.io/role/internal-elb,Value=1', connection_info, command_outputs)
            
        set_cluster_generic_property(dss_cluster_settings, 'alb-ingress.controller', 'true', True)

        return make_html(command_outputs)