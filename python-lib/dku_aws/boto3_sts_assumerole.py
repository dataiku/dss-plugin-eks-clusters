import boto3

class Boto3STSService(object):
    def __init__(self, arn):
        sess = boto3.Session()
        sts_connection = sess.client('sts')
        assume_role_object = sts_connection.assume_role(
            RoleArn=arn, RoleSessionName="test",
            DurationSeconds=3600)
        self.credentials = assume_role_object['Credentials']