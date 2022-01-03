from dataiku.runnables import Runnable
import dataiku
import json, logging, os
from dku_aws.eksctl_command import EksctlCommand
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_utils.access import _has_not_blank_property
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException
from dku_utils.access import _has_not_blank_property, _is_none_or_blank

class RunOnKubectl(Runnable):
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
        cmd = ['kubectl'] + self.config.get('args', [])
        if not _is_none_or_blank(self.config.get("namespace", "")):
            cmd = cmd + ["--namespace", self.config.get("namespace", "")]
        if not _is_none_or_blank(self.config.get("format", "")) and self.config.get("format", "") != 'none':
            cmd = cmd + ["-o", self.config.get("format", "")]
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=20)
            rv = 0
        except KubeCommandException as e:
            rv = e.rv
            out = e.out
            err = e.err
            
        out_html = '<div class="alert alert-info"><div>Output</div><pre class="debug" style="max-width: 100%%; max-height: 100%%;">%s</pre></div>' % out
        err_html = '<div class="alert alert-danger"><div>Error</div><pre class="debug" style="max-width: 100%%; max-height: 100%%;">%s</pre></div>' % err
        if rv == 0 or _is_none_or_blank(err):
            return out_html
        else:
            return ('<div class="alert alert-danger">Failed with code %s</div>' % rv) + err_html + out_html        