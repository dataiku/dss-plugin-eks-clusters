import logging
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
    if tags:
        tag_list = [key + '=' + value for key, value in tags.items()]
        args = args + ['--tags', ','.join(tag_list)]

    if node_pool.get('useSpotInstances', False):
        args = args + ['--managed', '--spot']

    if node_pool.get('publicKeyName', ''):
        args = args + ['--ssh-access']
        args = args + ['--ssh-public-key', node_pool.get('publicKeyName', '')]

    node_pool['labels'] = node_pool.get('labels', {})
    if node_pool['labels']:
        labels = []
        for label_key, label_value in node_pool['labels'].items():
            if not label_key:
                logging.error('At least one node pool label key is not valid, please ensure label keys are not empty. Observed labels: %s' % node_pool['labels'])
                raise Exception('At least one node pool label key is not valid, please ensure label keys are not empty. Observed labels: %s' % node_pool['labels'])
            if not label_value:
                label_value = ''
            labels.append('%s=%s' % (label_key, label_value))
        args += ['--node-labels', ','.join(labels)]

    return args

def get_node_pool_yaml(node_pool, networking_settings):
    yaml = {
        'iam': {
            'withAddonPolicies': {
                'imageBuilder': True # Adding full ECR access to the node group
            }
        }
    }
    if 'machineType' in node_pool:
        yaml['instanceType'] = node_pool['machineType']

    if 'diskType' in node_pool:
        yaml['volumeType'] = node_pool['diskType']

    if 'diskSizeGb' in node_pool and node_pool['diskSizeGb'] > 0:
        yaml['volumeSize'] = node_pool['diskSizeGb']
    else:
        yaml['volumeSize'] = 200 # also defined as default value in parameter-sets/node-pool-request/parameter-set.json

    yaml['desiredCapacity'] = node_pool.get('numNodes', 3)
    if node_pool.get('numNodesAutoscaling', False):
        yaml['iam']['withAddonPolicies']['autoScaler'] = True
        yaml['minSize'] = node_pool.get('minNumNodes', 2)
        yaml['maxSize'] = node_pool.get('maxNumNodes', 5)
        yaml['propagateASGTags'] = True

    yaml['tags'] = node_pool.get('tags', {})
    yaml['taints'] = build_node_pool_taints_yaml(node_pool)
    node_pool['labels'] = node_pool.get('labels', {})
    if any(_is_none_or_blank(label_key) for label_key in node_pool['labels'].keys()):
        logging.error('At least one node pool label key is not valid, please ensure label keys are not empty. Observed labels: [%s]' % ';'.join(node_pool['labels']))
        raise Exception('At least one node pool label key is not valid, please ensure label keys are not empty. Observed labels: [%s]' % ';'.join(node_pool['labels']))
    yaml['labels'] = node_pool['labels']
    yaml['spot'] = node_pool.get('useSpotInstances', False)

    sshPublicKeyName = node_pool.get('publicKeyName', None)
    if not _is_none_or_blank(sshPublicKeyName):
        yaml['ssh'] = {
            'allow': True,
            'publicKeyName': sshPublicKeyName
        }

    if networking_settings.get('securityGroups', []):
        yaml['securityGroups'] = {
            'attachIDs': list(map(lambda security_group: security_group.strip(), networking_settings['securityGroups']))
        }
    yaml['privateNetworking'] = networking_settings.get('privateNetworking', False)

    if node_pool.get('addPreBootstrapCommands', False) and not _is_none_or_blank(node_pool.get('preBootstrapCommands', None)):
        yaml['preBootstrapCommands'] = yaml.get('preBootstrapCommands', [])
        yaml['preBootstrapCommands'] += [command.strip()\
                                          for command in node_pool['preBootstrapCommands'].split('\n')\
                                              if not _is_none_or_blank(command)]

    return yaml

def build_node_pool_taints_yaml(node_pool):
    node_pool['taints'] = node_pool.get('taints', [])
    yaml_taints = []
    if node_pool['taints']:
        for taint in node_pool['taints']:
            if not _is_none_or_blank(taint.get('key', None)):
                yaml_taints.append({
                    'key': taint['key'],
                    'value': taint.get('value', ''),
                    'effect': taint.get('effect', 'NoSchedule')
                })
            else:
                logging.error('A node pool taint is invalid, please ensure that the key to a taint is not empty. Observed taints: [%s]' % ';'.join(node_pool['taints']))
                raise Exception('A node pool taint is invalid, please ensure that the key to a taint is not empty. Observed taints: [%s]' % ';'.join(node_pool['taints']))
    return yaml_taints