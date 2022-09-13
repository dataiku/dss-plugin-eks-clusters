from dataiku.runnables import Runnable
import os
import yaml
import json, logging
from dku_aws.aws_command import AwsCommand
from dku_utils.cluster import get_cluster_from_dss_cluster, get_cluster_generic_property, set_cluster_generic_property
from dku_utils.access import _has_not_blank_property
from dku_kube.kubectl_command import run_with_timeout, KubeCommandException
from dku_utils.access import _has_not_blank_property, _is_none_or_blank



class MyMacro(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config

      

    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])
       

        command_outputs = []
            
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")        
        
        cluster_id = cluster_def["Name"]
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides'][
            'kubeConfigPath']
        connection_info = dss_cluster_config.get('config', {}).get('connectionInfo', {})
        

        args = ['eks', 'update-kubeconfig']
        args = args + ['--name', str(self.config['clusterId'])]

        if _has_not_blank_property(connection_info, 'region'):
            args = args + ['--region', connection_info['region']]
        elif 'AWS_DEFAULT_REGION' is os.environ:
            args = args + ['--region', os.environ['AWS_DEFAULT_REGION']]

        c = AwsCommand(args, connection_info)
        command_outputs.append(c.run())
        if command_outputs[-1][1] != 0:
            return make_html(command_outputs)
        print(command_outputs)
        
        env = os.environ.copy()
        command = ['kubectl', 'set', 'env', 'daemonset', 'aws-node', '-n', 'kube-system', 'AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true']
        logging.info("Run : %s" % json.dumps(command))
        try:
            out, err = run_with_timeout(command, env=env, timeout=20)
            rv = 0
        except KubeCommandException as e:
            rv = e.rv
            out = e.out
            err = e.err
        
        #getting the list of subnets and AZs associated with it. Creating a Dict to pass it to ENIConfig template
        subnets = self.config.get('privateSubnets')
        securitygroup = self.config.get('securityGroup')
        
        sublist = []
        for subnet in subnets:
            t = {}
            t['enisub'] = subnet
            args = None
            args = ['ec2', 'describe-subnets']
            args = args + ['--subnet-ids', subnet]
            #args = args + ['| jq ".Subnets[].AvailabilityZone"']
            args = args + ['--query', 'Subnets[0].AvailabilityZone']
            c = None
            c = AwsCommand(args, connection_info)
            command_outputs = []
            command_outputs.append(c.run())
            print(command_outputs[0][2])
            t['az'] = command_outputs[0][2].strip().replace('"','')
            sublist.append(t)
        print(sublist)

            
        #empty list 

        #### empty ENI Config
        d = {'apiVersion':'crd.k8s.amazonaws.com/v1alpha1',
                     'kind':'ENIConfig',
                     'metadata':{'name':''},
                     'spec':{     
                    }
            }
        yamlCfg = ""
        for zone in sublist:
            eniCfg = d
            eniCfg['metadata']['name'] = zone['az']
            eniCfg['spec']['securityGroups'] = []
            for sg in securitygroup:
                eniCfg['spec']['securityGroups'].append(sg)
            eniCfg['spec']['subnet'] = zone['enisub']
            #print(eniCfg)
            yamlCfg += yaml.dump(eniCfg)
            yamlCfg += '---' + '\n'

        print(yamlCfg)    
        
        with open('/data/dataiku/data.yml', 'w',encoding = 'utf-8') as outfile:
            outfile.write(yamlCfg)
            #yaml.dump(yamlCfg, outfile, default_flow_style="False")
            #yaml.dump(yamlCfg, outfile, default_flow_style="False")
        
        cmd = ['kubectl', 'apply', '-f', '/data/dataiku/data.yml']
        logging.info("Run : %s" % json.dumps(cmd))
        try:
            out, err = run_with_timeout(cmd, env=env, timeout=20)
            rv = 0
        except KubeCommandException as e:
            rv = e.rv
            out = e.out
            err = e.err
        ancmd = ['kubectl', 'set', 'env', 'daemonset', 'aws-node', '-n', 'kube-system', 'ENI_CONFIG_LABEL_DEF=failure-domain.beta.kubernetes.io/zone']
        logging.info("Run : %s" % json.dumps(ancmd))
        try:
            out, err = run_with_timeout(ancmd, env=env, timeout=20)
            rv = 0
        except KubeCommandException as e:
            rv = e.rv
            out = e.out
            err = e.err
        
        
        
        #pass in self.config to get nodegroup. Set the Desire (if desire is > 0 scale to 0 )
        #aws ec2 terminate-instances --instance-ids $(aws ec2 describe-instances --query 'Reservations[].Instances[].InstanceId' --filters "Name=tag:tagkey,Values=tagvalue" --output text
        #r = $(aws ec2 describe-instances --query "Reservations[].Instances[].InstanceId" --filters "Name=eks:cluster-name,Values=nate4" --output text )
        
        args = []
        args = args + ['ec2', 'describe-instances']
        args = args + ['--query', 'Reservations[].Instances[].InstanceId']
        args = args + ['--filters', 'Name=tag:eks:cluster-name,Values={}'.format(self.config['clusterId'])]
        c = None
        c = AwsCommand(args, connection_info)
        command_outputs = []
        command_outputs.append(c.run())

   
        rsave = command_outputs[0][2].replace('\n',' ').replace('"','').replace(',','').replace('[','').replace(']','').split()


#        for kk in rsave:
#            args = []
#            args = ['ec2', 'terminate-instances', '--instance-ids', kk]
#            c = None
#            c = AwsCommand(args, connection_info)
#            command_outputs = []
#            command_outputs.append(c.run())

        

       
        
        
        #can get rid of it afterwards. Only used for testing syntax as successful return will not generate the output
        with open("test.yaml", "w") as f:
            f.write("""apiVersion: crd.k8s.amazonaws.com/v1alpha1
            kind: ENIConfig
            metadata:
              name: """ + "us-east-1a" + """
                spec:
            subnet: """ + str(s[0]) + """    #add multiple subnets 
              securityGroups:
              - """ + securitygroup)
            f.close()
        
        result = "success"
        return result