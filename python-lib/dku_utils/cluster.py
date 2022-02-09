from dku_utils.access import _default_if_blank, _default_if_property_blank
import dataiku
from dataiku.core.intercom import backend_json_call
from dku_utils.access import _has_not_blank_property
from dku_aws.boto3_sts_assumerole import Boto3STSService
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
    
def get_cluster_generic_property(dss_cluster_settings, key, default_value=None):
    props = dss_cluster_settings.settings['containerSettings']['executionConfigsGenericOverrides']['properties']
    found_value = default_value
    for prop in props:
        if prop['key'] == key:
            found_value = prop['value']
    return found_value

def set_cluster_generic_property(dss_cluster_settings, key, value, replace_if_exists=False):
    props = dss_cluster_settings.settings['containerSettings']['executionConfigsGenericOverrides']['properties']
    found_prop = None
    for prop in props:
        if prop['key'] == key:
            found_prop = prop
    if found_prop is None:
        props.append({'key':key, 'value':value})
        dss_cluster_settings.save()
    elif replace_if_exists:
        found_prop['value'] = value
        dss_cluster_settings.save()

def get_connection_info(config):
    # grab the ARN if it exists
    arn = config.get('assumeRoleARN', '')
    info = config.get('connectionInfo', {})
    # If the arn exists use boto3 to assumeRole to it, otherwise use the regular connection info
    if arn:
        connection_info = Boto3STSService(arn).credentials
        if _has_not_blank_property(info, 'region'):
            connection_info['region'] = info['region']
    else:
        connection_info = info
    return connection_info
