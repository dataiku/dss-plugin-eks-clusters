# Provide some utility methods to parse the saved configuration, clean it, normalize it and return in a predifined format (ex: command line args)

SECURITY_GROUPS = 'securityGroups'
SECURITY_GROUPS_ARG = '--node-security-groups'

# retrieves the EKS Cluster SecurityGroups (network param), remove all leading and trailing
# spaces and returns it as a eksctl command line argument
def getSecurityGroupsArg(config):
    if config is None or not isinstance(config, dict):
        raise Exception("config can not be null and has to be a dictionnary.")
    params = config.get(SECURITY_GROUPS, [])
    if len(params) > 0:
        params = list(map(str.strip, params))
        params = list(filter(None, params))
        return [SECURITY_GROUPS_ARG, ','.join(params)]
    return []
