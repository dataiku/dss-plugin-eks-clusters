from dataiku.runnables import Runnable
import os, sys, json, yaml, random, subprocess, socket, re, traceback, ipaddress
from dku_kube.busybox_pod import BusyboxPod
from dku_kube.kubectl_command import KubeCommandException
from dku_utils.cluster import get_cluster_from_dss_cluster
from six import text_type

class MyRunnable(Runnable):

    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, _ = get_cluster_from_dss_cluster(self.config['clusterId'])

        # the cluster is accessible via the kubeconfig
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']

        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        
        result = ''
        
        host = os.environ.get('DKU_BACKEND_EXT_HOST', socket.gethostname())
        port = os.environ['DKU_BACKEND_PORT']
        result = result + '<h5>Checking connectivity to %s:%s from pod in cluster</h5>' % (host, port)
        
        def add_to_result(result, op, cmd, out, err):
             return result + '<h5>%s</h5><div style="margin-left: 20px;"><div>Command</div><pre class="debug">%s</pre><div>Output</div><pre class="debug">%s</pre><div>Error</div><pre class="debug">%s</pre></div>' % (op, json.dumps(cmd), out, err)

        try:
            # sanity check
            if host.startswith("127.0.0") or 'localhost' in host:
                raise Exception('Host appears to not be a public hostname. Set DKU_BACKEND_EXT_HOST')
            with BusyboxPod(kube_config_path) as b:
                try:
                    ip = text_type(ipaddress.ip_address((host)))
                    result = result + '<h5>Host %s is an ip. No need to resolve it, testing connection directly</h5>' % (host)

                except ValueError:
                    # check that the pod resolved the hostname
                    ip = None
                    cmd = ['nslookup', host]
                    out, err = b.exec_cmd(cmd)
                    result =  result + '<h5>Resolve host</h5><div style="margin-left: 20px;"><div>Command</div><pre class="debug">%s</pre><div>Output</div><pre class="debug">%s</pre><div>Error</div><pre class="debug">%s</pre></div>' % (json.dumps(cmd), out, err)
                    for line in out.split('\n'):
                        m = re.match('^Address.*\\s([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+[^\\s]*)\\s.*$', line)
                        if m is not None:
                            ip = m.group(1)
                    if ip is None:
                        raise Exception('Hostname resolution of DSS node failed: %s' % out)
                    
                    result = result + '<h5>Host %s resolved to %s</h5>' % (host, ip)

                # try to connect on the backend port
                cmd = ['nc', '-vz', ip, port, '-w', '5']
                out, err = b.exec_cmd(cmd, timeout=10)
                result =  result + '<h5>Test connection to port</h5><div style="margin-left: 20px;"><div>Command</div><pre class="debug">%s</pre><div>Debug (stderr)</div><pre class="debug">%s</pre></div>' % (json.dumps(cmd), err)
                if 'no route to host' in err.lower():
                    raise Exception("DSS node resolved but unreachable on port %s : %s" % (str(port), err))

                result = result + '<h5>Connection successful</h5>'

        except KubeCommandException as e:
            traceback.print_exc()
            result = result + '<div class="alert alert-error"><div>%s</div><div>out:</div><pre>%s</pre><div>err:</div><pre>%s</pre></div>' % (str(e), e.out, e.err)
        except Exception as e:
            traceback.print_exc()
            result = result + '<div class="alert alert-error">%s</div>' % str(e)
                
        return '<div>%s</div>' % result
