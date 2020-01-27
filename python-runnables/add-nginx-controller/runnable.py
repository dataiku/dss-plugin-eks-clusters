from dataiku.runnables import Runnable
import dataiku
import json, logging, os, re, tempfile
import requests
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_utils.access import _has_not_blank_property
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException
from dku_utils.access import _has_not_blank_property, _is_none_or_blank

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
    return '\n'.join(divs)

class InstallNginx(Runnable):
    """
    Installs a Nginx ingress controller as described in https://kubernetes.github.io/ingress-nginx/deploy
    """
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])

        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']

        env = os.environ.copy()
        env['KUBECONFIG'] = kube_config_path
        
        command_outputs = []
        keep_going = True
        
        cmd = ['kubectl', 'apply', '-f', 'https://raw.githubusercontent.com/kubernetes/ingress-nginx/nginx-0.27.1/deploy/static/mandatory.yaml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=20)
            command_outputs.append((cmd, 0, out, err))
        except KubeCommandException as e:
            command_outputs.append((cmd, e.rv, e.out, e.err))
            keep_going = False

        if not keep_going:
            return make_html(command_outputs)
            
        idle_timeout_pattern = 'service.beta.kubernetes.io/aws\\-load\\-balancer\\-connection\\-idle\\-timeout:\\s*"[0-9]+"'
        idle_timeout_replacement = 'service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout: "%s"' % self.config.get('idleTimeout', 60)
        if self.config.get('layer', 'L4') == 'L7':
            r = requests.get('https://raw.githubusercontent.com/kubernetes/ingress-nginx/nginx-0.27.1/deploy/static/provider/aws/service-l7.yaml')
            service_data = r.content
            service_data = re.sub(idle_timeout_pattern, idle_timeout_replacement, service_data)
            cert_pattern = 'service.beta.kubernetes.io/aws\\-load\\-balancer\\-ssl\\-cert:\\s*".*"'
            cert_replacement = 'service.beta.kubernetes.io/aws\\-load\\-balancer\\-ssl\\-cert: "%s"' % self.config.get('certificate', '')
            service_data = re.sub(cert_pattern, cert_replacement, service_data)
            with open('./service-l7.yaml', 'w') as f:
                f.write(service_data)
                
            cmd = ['kubectl', 'apply', '-f', './service-l7.yaml']
            logging.info("Run : %s" % json.dumps(cmd))
            try:
                out, err = run_with_timeout(cmd, env=env, timeout=20)
                command_outputs.append((cmd, 0, out, err))
            except KubeCommandException as e:
                command_outputs.append((cmd, e.rv, e.out, e.err))
                keep_going = False

            if not keep_going:
                return make_html(command_outputs)
            
            cmd = ['kubectl', 'apply', '-f', 'https://raw.githubusercontent.com/kubernetes/ingress-nginx/nginx-0.27.1/deploy/static/provider/aws/patch-configmap-l7.yaml']
            logging.info("Run : %s" % json.dumps(cmd))
            try:
                out, err = run_with_timeout(cmd, env=env, timeout=20)
                command_outputs.append((cmd, 0, out, err))
            except KubeCommandException as e:
                command_outputs.append((cmd, e.rv, e.out, e.err))

        else:
            r = requests.get('https://raw.githubusercontent.com/kubernetes/ingress-nginx/nginx-0.27.1/deploy/static/provider/aws/service-l4.yaml')
            service_data = r.content
            service_data = re.sub(idle_timeout_pattern, idle_timeout_replacement, service_data)
            with open('./service-l4.yaml', 'w') as f:
                f.write(service_data)
                
            cmd = ['kubectl', 'apply', '-f', './service-l4.yaml']
            logging.info("Run : %s" % json.dumps(cmd))
            try:
                out, err = run_with_timeout(cmd, env=env, timeout=20)
                command_outputs.append((cmd, 0, out, err))
            except KubeCommandException as e:
                command_outputs.append((cmd, e.rv, e.out, e.err))
                keep_going = False

            if not keep_going:
                return make_html(command_outputs)
            
            cmd = ['kubectl', 'apply', '-f', 'https://raw.githubusercontent.com/kubernetes/ingress-nginx/nginx-0.27.1/deploy/static/provider/aws/patch-configmap-l4.yaml']
            logging.info("Run : %s" % json.dumps(cmd))
            try:
                out, err = run_with_timeout(cmd, env=env, timeout=20)
                command_outputs.append((cmd, 0, out, err))
            except KubeCommandException as e:
                command_outputs.append((cmd, e.rv, e.out, e.err))

        # all ready, flag the cluster as nginx-able
        dss_cluster_id = self.config['clusterId']
        # get the public API client
        client = dataiku.api_client()
        # get the cluster object in DSS
        found = False
        for c in client.list_clusters():
            if c['name'] == dss_cluster_id:
                found = True
        if not found:
            raise Exception("DSS cluster %s doesn't exist" % dss_cluster_id)
        dss_cluster = client.get_cluster(dss_cluster_id)
        dss_cluster_settings = dss_cluster.get_settings()
        props = dss_cluster_settings.settings['containerSettings']['executionConfigsGenericOverrides']['properties']
        has_prop = False
        for prop in props:
            if prop['key'] == 'nginx-ingress.controller':
                has_prop = True
        if not has_prop:
            props.append({'key':'nginx-ingress.controller', 'value':'true'})
            dss_cluster_settings.save()
            
        return make_html(command_outputs)
                
                