# Provide some utility methods to parse the saved configuration, clean it,
# normalize it and return in a predifined format (ex: command line args)

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

    params = list(map(str.strip, params))
    params = list(filter(None, params))
    return [SECURITY_GROUPS_ARG, ','.join(params)]
