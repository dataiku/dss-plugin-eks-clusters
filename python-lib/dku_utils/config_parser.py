# Provide some utility methods to parse the saved configuration, clean it,
# normalize it and return in a predefined format (ex: command line args)

import os, logging, requests, json
from dku_utils.access import _has_not_blank_property

SECURITY_GROUPS = 'securityGroups'
SECURITY_GROUPS_ARG = '--node-security-groups'

def get_security_groups_arg(config):
    """
    retrieves the EKS Cluster SecurityGroups (network param),
    removes all leading and trailing spaces
    removes empty groups (which contain only spaces)
    :param dict config: eks cluster settings
    :return: the eksctl securityGroups command line argument
    """
    if config is None or not isinstance(config, dict):
        raise Exception("config can not be null and has to be a dictionary.")
    params = config.get(SECURITY_GROUPS, [])
    if len(params) == 0:
        return []

    params = list(map(lambda param: param.strip(), params))
    params = list(filter(None, params))
    return [SECURITY_GROUPS_ARG, ','.join(params)]


REGION_ARG = "--region"

def get_region_fallback_to_metadata(connection_info):
    if _has_not_blank_property(connection_info, 'region'):
        logging.info("Using region %s" % connection_info['region'])
        return connection_info['region']
    if 'AWS_DEFAULT_REGION' in os.environ:
        logging.info("Using AWS_DEFAULT_REGION %s" % os.environ['AWS_DEFAULT_REGION'])
        return os.environ['AWS_DEFAULT_REGION']
    try:
        imds_token = requests.put("http://169.254.169.254/latest/api/token", headers = {'X-aws-ec2-metadata-token-ttl-seconds': '2160'}).text
        document = requests.get("http://169.254.169.254/latest/dynamic/instance-identity/document", headers={ 'X-aws-ec2-metadata-token': imds_token}).text
        return json.loads(document).get('region')
    except Exception as e:
        logging.error("Failed to get region from metadata: %s" % str(e))
    return None

def get_region_arg(connection_info):
    region = get_region_fallback_to_metadata(connection_info)
    if region is not None:
        return [REGION_ARG, region]
    return []

def get_private_ip_from_metadata():
    try:
        imds_token = requests.put("http://169.254.169.254/latest/api/token", headers = {'X-aws-ec2-metadata-token-ttl-seconds': '2160'}).text
        document = requests.get("http://169.254.169.254/latest/dynamic/instance-identity/document", headers={ 'X-aws-ec2-metadata-token': imds_token}).text
        return json.loads(document).get('privateIp')
    except Exception as e:
        logging.error("Failed to get region from metadata: %s" % str(e))
    return None

