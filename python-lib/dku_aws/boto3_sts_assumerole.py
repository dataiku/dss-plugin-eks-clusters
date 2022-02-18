import boto3

class Boto3STSService(object):
    def __init__(self, arn):
        sess = boto3.Session()
        sts_connection = sess.client('sts')
        assume_role_object = sts_connection.assume_role(
            RoleArn=arn, RoleSessionName="DSS-EKS-Plugin",
            DurationSeconds=3600)
        creds = assume_role_object['Credentials']
        creds['accessKey'] = creds.pop('AccessKeyId')
        creds['secretKey'] = creds.pop('SecretAccessKey')
        creds['sessionToken'] = creds.pop('SessionToken')
        self.credentials = creds
        