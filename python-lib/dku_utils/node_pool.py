from dku_utils.access import _is_none_or_blank

def get_node_pool_args(node_pool):
    args = []
    if 'machineType' in node_pool:
        args = args + ['--node-type', node_pool['machineType']]
    if 'diskType' in node_pool:
        args = args + ['--node-volume-type', node_pool['diskType']]
    if 'diskSizeGb' in node_pool and node_pool['diskSizeGb'] > 0:
        disk_size_gb = node_pool['diskSizeGb']
    else:
        disk_size_gb = 200 # also defined as default value in parameter-sets/node-pool-request/parameter-set.json
    args = args + ['--node-volume-size', str(disk_size_gb)]

    args = args + ['--nodes', str(node_pool.get('numNodes', 3))]
    if node_pool.get('numNodesAutoscaling', False):
        args = args + ['--asg-access']
        args = args + ['--nodes-min', str(node_pool.get('minNumNodes', 2))]
        args = args + ['--nodes-max', str(node_pool.get('maxNumNodes', 5))]

    tags = node_pool.get('tags', {})
    if len(tags) > 0:
        tag_list = [key + '=' + value for key, value in tags.items()]
        args = args + ['--tags', ','.join(tag_list)]

    if node_pool.get('useSpotInstances', False):
        args = args + ['--managed', '--spot']

    if len(node_pool.get('publicKeyName', '')) > 0:
        args = args + ["--ssh-access"]
        args = args + ['--ssh-public-key', node_pool.get('publicKeyName', '')]

    if bool(node_pool.get('labels', {})):
        args += ['--node-labels', ','.join(['%s=%s' % (label_key, label_value) for label_key, label_value in node_pool['labels'].items()])]

    return args

def get_node_pool_yaml(node_pool, networking_settings):
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
            'withAddonPolicies': {
                'autoScaler': True
            }
        }
        yaml['minSize'] = node_pool.get('minNumNodes', 2)
        yaml['maxSize'] = node_pool.get('maxNumNodes', 2)

    yaml['tags'] = node_pool.get('tags', {})
    yaml['taints'] = build_node_pool_taints_yaml(node_pool)
    yaml['labels'] = node_pool.get('labels', dict())
    yaml['spot'] = node_pool.get('useSpotInstances', False)

    sshPublicKeyName = node_pool.get('publicKeyName', '')
    if not _is_none_or_blank(sshPublicKeyName):
        yaml['ssh'] = {
            'allow': True,
            'publicKeyName': sshPublicKeyName,
            # Should we enable SSM??
        }

    if len(networking_settings.get('securityGroups', [])) > 0:
        yaml['securityGroups'] = {
            'attachIDs': networking_settings['securityGroups']
        }
    yaml['privateNetworking'] = networking_settings.get('privateNetworking', False)

    if node_pool.get('addPreBootstrapCommands', False) and not _is_none_or_blank(node_pool.get("preBootstrapCommands", "")):
        yaml['preBootstrapCommands'] = yaml.get('preBootstrapCommands', [])
        yaml['preBootstrapCommands'] += [command.strip()\
                                          for command in node_pool['preBootstrapCommands'].split('\n')\
                                              if not _is_none_or_blank(command.strip())]

    return yaml

def build_node_pool_taints_yaml(node_pool):
    node_pool['taints'] = node_pool.get('taints', [])
    yaml_taints = []
    if len(node_pool['taints']) > 0:
        for taint in node_pool['taints']:
            if not _is_none_or_blank(taint.get('key', '')):
                yaml_taints.append({
                    'key': taint['key'],
                    'value': taint['value'],
                    'effect': taint['effect']
                })
    return yaml_taints