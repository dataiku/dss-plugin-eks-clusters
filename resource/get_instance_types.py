def do(payload, config, plugin_config, inputs):
    from dku_aws.boto3_command import get_instances_and_spot, build_choice_list

    instances_df = get_instances_and_spot()
    instances_df = instances_df[['Instance_Type','vCPUs','Memory','GPU_Ind','Processor_Speed','Current_Spot_Price','Instance_Recommended']]
    instances_df = instances_df.sort_values(by=['Instance_Recommended', 'GPU_Ind', 'vCPUs', 'Memory', 'Processor_Speed', 'Current_Spot_Price'], ascending=[False, True, True, False, False, True])

    instances_df['Inst_Description'] = (
        instances_df['Instance_Type'] + '/' + 
        'vCPUs:' + instances_df['vCPUs'].astype(str) + '/' + 
        'Mem:' + instances_df['Memory'].astype(str) + '/' + 
        'Ghz:' + instances_df['Processor_Speed'].astype(str) + '/' + 
        'Spot: $' + instances_df['Current_Spot_Price'].astype(str) + '/' + 
        'GPU:' + instances_df['GPU_Ind'].astype(str) )

    Inst_Type = instances_df['Instance_Type'].tolist()
    Inst_Desc = instances_df['Inst_Description'].tolist()
    
    Inst_Type = 'r5b.large'
    Inst_Desc = 'r5b.large/vCPUs:2/Mem:16.0/Ghz:3.1/Spot: $0.020900/GPU:0.0'

    choices=[]
    
    choices.append({"value: {}, label: {}".format(Inst_Type, Inst_Desc)})
    
    Inst_Type = 'r5a.large'
    Inst_Desc = 'r5a.large/vCPUs:2/Mem:16.0/Ghz:3.1/Spot: $0.020900/GPU:0.0'   
    
    choices.append({"value: {}, label: {}".format(Inst_Type, Inst_Desc)})
    
    #choices = dict(zip(instances_df['Instance_Type'],instances_df['Inst_Description']))
    #choices += dict(zip([{"label": Inst_Type, "value": Inst_Desc}])
    
    choices

    return {"choices": choices}