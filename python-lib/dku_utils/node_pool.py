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
        
    return args