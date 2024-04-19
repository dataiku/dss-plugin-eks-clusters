from dataiku.runnables import Runnable
import dataiku
import os, json, logging
from dku_kube.autoscaler import add_autoscaler_if_needed, has_autoscaler
from dku_utils.cluster import get_cluster_from_dss_cluster

class MyRunnable(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])

        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        cluster_id = cluster_def["Name"]

        # the cluster is accessible via the kubeconfig
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']
        
        if has_autoscaler(kube_config_path):
            return '<h5>An autoscaler pod already runs<h5>'
        else:
            add_autoscaler_if_needed(cluster_id, self.config, cluster_def, kube_config_path, [])
            return '<h5>Created an autoscaler pod<h5>'
