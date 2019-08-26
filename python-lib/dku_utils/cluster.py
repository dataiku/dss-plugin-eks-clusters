from dku_utils.access import _default_if_blank, _default_if_property_blank
import dataiku
from dataiku.core.intercom import backend_json_call
from dku_utils.access import _has_not_blank_property
import json, logging

def make_overrides(config, kube_config, kube_config_path):
    # alter the spark configurations to put the cluster master and image repo in the properties
    container_settings = {
                            'executionConfigsGenericOverrides': {
                                'kubeCtlContext': kube_config["current-context"], # has to exist, it's a config file we just built
                                'kubeConfigPath': kube_config_path, # the config is not merged into the main config file, so we need to pass the config file pth
                                'baseImage': _default_if_property_blank(config, "baseImage", None),
                                'repositoryURL': _default_if_property_blank(config, "repositoryURL", None)
                            }
                        }
    return {'container':container_settings}

def get_cluster_from_dss_cluster(dss_cluster_id):
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

    # get the settings in it
    dss_cluster_settings = dss_cluster.get_settings()
    dss_cluster_config = dss_cluster_settings.get_raw()['params']['config']
    # resolve since we get the config with the raw preset setup
    dss_cluster_config = backend_json_call('plugins/get-resolved-settings', data={'elementConfig':json.dumps(dss_cluster_config), 'elementType':dss_cluster_settings.get_raw()['type']})
    logging.info("Resolved cluster config : %s" % json.dumps(dss_cluster_config))

    cluster_data = dss_cluster_settings.get_plugin_data()

    return cluster_data, dss_cluster_settings, dss_cluster_config
    
