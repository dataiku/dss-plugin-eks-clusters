import os, sys, json, yaml, logging, random, time
from .kubectl_command import run_with_timeout

class BusyboxPod(object):
    def __init__(self, kube_config_path):
        self.env = os.environ.copy()
        self.env['KUBECONFIG'] = kube_config_path
        uid = ''.join([random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in range(0,8)])
        self.pod_name = "busybox-" + uid
        
    def __enter__(self):
        # create pod
        pod_yaml = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": self.pod_name,
                "namespace": "default"
            },
            "spec": {
                "containers": [
                    {
                        "name": self.pod_name,
                        "image": "busybox:1.28",
                        "command": ["sleep", "3600"],
                        "imagePullPolicy": "IfNotPresent"
                    }
                ],
                "restartPolicy": "Always"
            }
        }
        pod_file_path = 'busybox_pod.yaml'
        with open(pod_file_path, "w") as f:
            yaml.safe_dump(pod_yaml, f)

        cmd = ['kubectl', 'create', '-f', os.path.abspath(pod_file_path)]
        logging.info("Create pod with : %s" % json.dumps(cmd))
        run_with_timeout(cmd, env=self.env, timeout=5)
        
        # wait for it to actually run (could be stuck in pending if no resource available)
        waited = 0
        pod_state = self.get_pod_state()
        while pod_state != 'running' and waited < 10:
            time.sleep(1)
            waited += 1
            pod_state = self.get_pod_state()
        
        if pod_state != 'running':
            self.delete_pod()
            raise Exception('Busybox did not start in 10s')
            
        return self
    
    def get_pod_state(self):
        cmd = ['kubectl', 'get', 'pod', self.pod_name, '-o', 'json']
        logging.info("Poll pod state with : %s" % json.dumps(cmd))
        out, err = run_with_timeout(cmd, env=self.env, timeout=5)
        return json.loads(out)['status']['phase'].lower()

    def delete_pod(self):
        cmd = ['kubectl', 'delete', 'pods', self.pod_name]
        logging.info("Delete pod with : %s" % json.dumps(cmd))
        run_with_timeout(cmd, env=self.env, timeout=3, nokill=True) # fire and forget
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.delete_pod()
        logging.info("Exited busybox")
        return False
    
    def exec_cmd(self, cmd, timeout=5):
        kcmd = ['kubectl', 'exec', self.pod_name, '--'] + cmd
        logging.info("Execute in pod with : %s" % json.dumps(kcmd))
        out, err = run_with_timeout(kcmd, env=self.env, timeout=timeout)
        return out, err
    