# This file is the actual code for the Python runnable install-nvidia-driver
from dataiku.runnables import Runnable
from dku_utils.cluster import get_cluster_from_dss_cluster
import os
import subprocess

class MyRunnable(Runnable):
    """The base interface for a Python runnable"""

    def __init__(self, project_key, config, plugin_config):
        """
        :param project_key: the project in which the runnable executes
        :param config: the dict of the configuration of the object
        :param plugin_config: contains the plugin settings
        """
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        """
        If the runnable will return some progress info, have this function return a tuple of 
        (target, unit) where unit is one of: SIZE, FILES, RECORDS, NONE
        """
        return None

    def run(self, progress_callback):
        """
        Do stuff here. Can return a string or raise an exception.
        The progress_callback is a function expecting 1 value: current progress
        """
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])
        
        os.environ["KUBECONFIG"] = cluster_data["kube_config_path"]
        
        proc = subprocess.Popen(
            ["kubectl", "apply", "-f", "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/master/nvidia-device-plugin.yml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = proc.communicate()
        
        del os.environ["KUBECONFIG"]
        
        if stderr:
            raise Exception("Exception installing driver: {}".format(stderr))
            
        return "Success!"
        