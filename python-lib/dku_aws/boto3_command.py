import sys, os, subprocess, logging, json, requests, shutil, boto3, json, tabulate, urllib.request, re, math
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dku_utils.access import _has_not_blank_property


def dataiku_recommended_instance_type(instance_type, gpu_ind=0):

    
    instance_type = instance_type.strip()
    sr = re.search(r"\d", instance_type)
    idx_fam = sr.start()
    instance_family = instance_type[:idx_fam]

    instance_family = instance_family.lower()
    if instance_family in ['m','r','c'] and gpu_ind==0:
        recommend = 1
    
    elif instance_family in ['p','inf','g'] and gpu_ind==1:
        recommend = 1

    else:
        recommend = 0
    
    return recommend

def split_fsg(instance_type, flg):

    sr = re.search(r"\d", instance_type)
    idx_fam = sr.start()
    instance_family = instance_type[:idx_fam]
    idx_series = instance_type.find('.',0)
    instance_series = instance_type[:idx_series]
    
    temp = re.findall(r'\d+', instance_type)
    res = list(map(int, temp))
    instance_generation = res[0]
    if flg == 'f':
        var = instance_family
    elif flg == 's':
        var = instance_series
    elif flg == 'g':
        var = instance_generation
    else :
        var = None


    return var

def get_dss_instance_variables ():
    ec2_client = boto3.client('ec2')
    dss_region = ec2_client.meta.region_name
    current_date_time = datetime.now()
    strt_dt_window = current_date_time + timedelta(days = -31)

    """
    Get the DSS Instance ID. Will use this to track back to the availability zone of the instance.
    When we create Spot node groups will create them in the same AZ as DSS, lowering data transfer costs.
    """

    dss_instance_id = urllib.request.urlopen('http://169.254.169.254/latest/meta-data/instance-id').read().decode()

    # -------------------------------------------------------------------------------- NOTEBOOK-CELL: CODE
    paginator = ec2_client.get_paginator('describe_instances')
    response = paginator.paginate().build_full_result()

    for reservation in response['Reservations']:
      for instance in reservation['Instances']:
        instance_id = instance['InstanceId']
        if dss_instance_id == instance_id :
            place = instance['Placement']
            dss_availability_zone = place['AvailabilityZone']
            
    d = {}
    
    d = {'instance_id': dss_instance_id, 'region': dss_region, 'availability_zone': dss_availability_zone, 'current_dt': current_date_time, 'strt_dt_window': strt_dt_window}
    
    return d


def get_instances_and_spot():
    ec2_client = boto3.client('ec2')
    dss_instance = get_dss_instance_variables()
    dss_region = dss_instance['region']
    dss_availability_zone = dss_instance['availability_zone']
    current_date_time = dss_instance['current_dt']
    
    paginator = ec2_client.get_paginator('describe_instance_types')
    page_iterator = paginator.paginate(
        Filters=[{"Name": "processor-info.supported-architecture", "Values": ["x86_64"]},
            {"Name": "supported-usage-class", "Values": ["spot"]}
            ])

    filtered_iterator = page_iterator.search('InstanceTypes[?MemoryInfo.SizeInMiB > `4000` ].[InstanceType, VCpuInfo.DefaultVCpus, MemoryInfo.SizeInMiB, GpuInfo.TotalGpuMemoryInMiB, ProcessorInfo.SustainedClockSpeedInGhz, VCpuInfo.DefaultCores, VCpuInfo.DefaultThreadsPerCore]')

    instdf = pd.DataFrame()
    instdf = instdf.from_records(filtered_iterator)
    instdf = instdf.rename(columns={0 : "Instance_Type", 1 : "vCPUs", 2 : "Memory", 3 : "GPU_Ind", 4: "Processor_Speed", 5: "Cores", 6: "Threads"}) 
    
    instance_family = [split_fsg(x, 'f') for x in instdf['Instance_Type']]
    instance_series = [split_fsg(x, 's') for x in instdf['Instance_Type']]
    instance_generation = [split_fsg(x, 'g') for x in instdf['Instance_Type']]
    instance_recommend = [dataiku_recommended_instance_type(x) for x in instdf['Instance_Type']]

    instdf['Instance_Family'] = instance_family
    instdf['Instance_Series'] = instance_series
    instdf['Instance_Generation'] = instance_generation
    instdf['Instance_Recommended'] = instance_recommend


    memory = instdf['Memory'].astype('float64')
    memory = memory / 1024.0
    instdf['Memory'] = memory

    instdf['GPU_Ind'] = instdf["GPU_Ind"] / instdf["GPU_Ind"]
    instdf['GPU_Ind'] = instdf.GPU_Ind.fillna(0)
  
    instdf = instdf.sort_values(by=['Instance_Family', 'vCPUs', 'Instance_Generation'], ascending=[True, True, False])

    spot_list = instdf['Instance_Type'].values.tolist()

    paginator = ec2_client.get_paginator('describe_spot_price_history')

    response_iterator = paginator.paginate(
        AvailabilityZone = dss_availability_zone,
        StartTime = current_date_time,
        ProductDescriptions = ['Linux/UNIX'],
        InstanceTypes= spot_list
    )

    filtered_iterator = response_iterator.search('SpotPriceHistory[].[InstanceType, AvailabilityZone, SpotPrice, Timestamp]')

    spothist = pd.DataFrame()
    spothist = spothist.from_records(filtered_iterator)
    spothist = spothist.rename(columns={0 : "Instance_Type", 1 : "Region", 2 : "Current_Spot_Price", 3 : "Last_Update (UTC)"})
    spothist = spothist.sort_values(by=['Instance_Type', 'Current_Spot_Price'], ascending=[True, True])
    spothist = spothist.groupby('Instance_Type').first()

    total_spot_df = pd.merge(instdf, spothist, how="inner", on=["Instance_Type"])
    total_spot_df = total_spot_df.sort_values(by=['vCPUs', 'Memory', 'Current_Spot_Price'], ascending=[True, False, True])

    return total_spot_df


