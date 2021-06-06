import sys, os, subprocess, logging, json, requests, shutil, boto3, json, tabulate, urllib.request, re, math
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dku_utils.access import _has_not_blank_property


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