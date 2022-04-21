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

class RemoveAlb(Runnable):
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

        if get_cluster_generic_property(dss_cluster_settings, 'alb-ingress.controller', 'false') != 'true':
            raise Exception("ALB controller not installed (or not by the installation macro)")

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
        
        # delete the controller
        cmd = ['kubectl', 'delete', '-f', 'https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.4/docs/examples/alb-ingress-controller.yaml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=100)
            command_outputs.append((cmd, 0, out, err))
        except KubeCommandException as e:
            command_outputs.append((cmd, e.rv, e.out, e.err))
            keep_going = False

        if not keep_going:
            return make_html(command_outputs)

        # detach the role from the policy
        args = ['delete', 'iamserviceaccount']
        #args = args + ['-v', '4']
        args = args + ['--name', 'alb-ingress-controller'] # that's the name in the rbac-role.yaml
        args = args + ['--namespace', 'kube-system'] # that's the name in the rbac-role.yaml
        args = args + ['--cluster', cluster_id]
        args = args + get_region_arg(connection_info)

        c = EksctlCommand(args, connection_info)
        command_outputs.append(c.run())
        if command_outputs[-1][1] != 0:
            return make_html(command_outputs)
        
        # delete the role on the cluster
        cmd = ['kubectl', 'delete', '-f', 'https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.4/docs/examples/rbac-role.yaml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=100)
            command_outputs.append((cmd, 0, out, err))
        except KubeCommandException as e:
            command_outputs.append((cmd, e.rv, e.out, e.err))

        set_cluster_generic_property(dss_cluster_settings, 'alb-ingress.controller', 'false', True)

        return make_html(command_outputs)