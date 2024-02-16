from dku_utils.access import _is_none_or_blank

def get_node_pool_yaml(node_pool):
    yaml = {}
    if 'machineType' in node_pool:
        yaml['instanceType'] = node_pool['machineType']
    yaml['volumeType'] = node_pool.get('diskType', 'gp2')
    if 'diskSizeGb' in node_pool and node_pool['diskSizeGb'] > 0:
        yaml['volumeSize'] = node_pool['diskSizeGb']
    else:
        yaml['volumeSize'] = 200 # also defined as default value in parameter-sets/node-pool-request/parameter-set.json

    yaml['desiredCapacity'] = node_pool.get('numNodes', 3)
    if node_pool.get('numNodesAutoscaling', False):
        yaml['iam'] = {
            'withAddOnPolicies': {
                'autoScaler': True
            }
        }
        yaml['minSize'] = node_pool.get('minNumNodes', 2)
        yaml['maxSize'] = node_pool.get('maxNumNodes', 2)

    tags = node_pool.get('tags', {})
    if len(tags) > 0:
        yaml['tags'] = [ { key: value } for key, value in tags.items()]

    yaml['spot'] = node_pool.get('useSpotInstances', False)

    sshPublicKeyName = node_pool.get('publicKeyName', '')
    if len(sshPublicKeyName) > 0:
        yaml['ssh'] = {
            'allow': True,
            'publicKey': sshPublicKeyName,
            # Should we enable SSM??
        }

    if node_pool.get('addPreBootstrapCommands', False) and not _is_none_or_blank(node_pool.get("preBootstrapCommands", "")):
        node_pool['preBootstrapCommands'] = [command.strip() for command in node_pool['preBootstrapCommands'].split('\n') if len(command.strip()) > 0]

    return yaml