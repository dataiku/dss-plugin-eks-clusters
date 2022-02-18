import os, sys, json, yaml, logging
from dku_utils.access import _has_not_blank_property, _is_none_or_blank

def get_first_kube_config(kube_config_path=None):
    if kube_config_path is None:
        if _has_not_blank_property(os.environ, 'KUBECONFIG'):
            kube_config_path = os.environ['KUBECONFIG'].split(':')[0]
        else:
            kube_config_path = os.path.join(os.environ['HOME'], '.kube', 'config')
    return kube_config_path

def merge_or_write_config(config, kube_config_path=None):
    kube_config_path = get_first_kube_config(kube_config_path)

    if os.path.exists(kube_config_path):
        logging.info("A kube config exists at %s => merging" % kube_config_path)
        with open(kube_config_path, "r") as f:
            existing = yaml.safe_load(f)
        for k in ['users', 'clusters', 'contexts']:
            elements = existing.get(k, [])
            existing[k] = elements
            new_elements = config.get(k, [])
            for new_element in new_elements:
                name = new_element.get("name", "")
                element_idx = None
                for i in range(0, len(elements)):
                    if elements[i].get("name", None) == name:
                        element_idx = i
                logging.info("  %s > %s : %s" % (k, name, 'replace' if element_idx is not None else 'append'))
                if element_idx is not None:
                    elements[element_idx] = new_element
                else:
                    elements.append(new_element)
        """
        if len(config.get("current-context", "")) > 0:
            current_context = config.get("current-context")
            logging.info("Setting current context to %s" % current_context)
            existing["current-context"] = current_context
        """

        logging.info("Final state is %s" % json.dumps(existing, indent=2))

        with open(kube_config_path, "w") as f:
            yaml.safe_dump(existing, f)
    else:
        logging.info("No kube config file found at %s => writing" % kube_config_path)

        with open(kube_config_path, "w") as f:
            yaml.safe_dump(config, f)

def add_authenticator_env(kube_config_path, env):
    with open(kube_config_path, "r") as f:
        existing = yaml.safe_load(f)
    if 'exec' in existing['users'][0]['user']:
        authenticator = existing['users'][0]['user']['exec']
        authenticator_env = authenticator.get('env', [])
        if authenticator_env is None:
            authenticator_env = []
        for k in env:
            authenticator_env.append({'name':k, 'value':env[k]})
        authenticator['env'] = authenticator_env
    with open(kube_config_path, "w") as f:
        yaml.safe_dump(existing, f)

def add_assumed_arn(kube_config_path, arn):
    with open(kube_config_path, "r") as f:
        existing = yaml.safe_load(f)
    if 'exec' in existing['users'][0]['user']:
        existing['users'][0]['user']['exec']['args'].extend(['-r',arn])
    with open(kube_config_path, "w") as f:
        yaml.safe_dump(existing, f)

def setup_creds_env(kube_config_path, connection_info, config):
    # If the arn exists, then add it to the kubeconfig so it is the assumed role for future use
    arn = config.get('assumeRoleARN', '')
    if arn:
        logging.info("Assuming role %s" % arn)
        add_assumed_arn(kube_config_path, arn)
    elif _has_not_blank_property(connection_info, 'accessKey') and _has_not_blank_property(connection_info, 'secretKey'):
        creds_in_env = {'AWS_ACCESS_KEY_ID':connection_info['accessKey'], 'AWS_SECRET_ACCESS_KEY':connection_info['secretKey']}
        add_authenticator_env(kube_config_path, creds_in_env)
