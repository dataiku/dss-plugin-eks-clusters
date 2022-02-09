# Provide some utility methods to parse the saved configuration, clean it,
# normalize it and return in a predefined format (ex: command line args)

import os, logging
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

def get_region_arg(connection_info):
    if _has_not_blank_property(connection_info, 'region'):
        logging.info("Using region %s" % connection_info['region'])
        return [REGION_ARG, connection_info['region']]
    elif 'AWS_DEFAULT_REGION' in os.environ:
        logging.info("Using AWS_DEFAULT_REGION %s" % os.environ['AWS_DEFAULT_REGION'])
        return [REGION_ARG, os.environ['AWS_DEFAULT_REGION']]
    return []
