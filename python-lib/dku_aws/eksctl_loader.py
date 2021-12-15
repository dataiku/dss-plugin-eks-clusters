import sys, os, subprocess, logging, json, requests, shutil

def get_eksctl_or_fetch():
    try:
        machine_eksctl = subprocess.check_output(["which", "eksctl"]).strip().decode('utf8')
        logging.info("Found eksctl on the machine")
        return machine_eksctl
    except:
        local_eksctl_folder = os.path.join(os.environ["DIP_HOME"], 'tmp', 'local_eksctl')
        logging.info("Using eksctl from %s" % local_eksctl_folder)
        local_eksctl = os.path.join(local_eksctl_folder, 'eksctl')
        if not os.path.exists(local_eksctl_folder):
            os.makedirs(local_eksctl_folder)
        if not os.path.exists(local_eksctl):
            arch = subprocess.check_output(["uname", "-s"]).strip().decode('utf8')
            logging.info("Downloading eksctl for %s" % arch)
            r = requests.get("https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_%s_amd64.tar.gz" % arch, stream=True)
            local_eksctl_archive = os.path.join(local_eksctl_folder, 'eksctl.tar.gz')
            with open(local_eksctl_archive, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
            subprocess.check_call(["tar", "-xzf", local_eksctl_archive], cwd=local_eksctl_folder)
        return local_eksctl
