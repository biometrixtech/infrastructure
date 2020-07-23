from colorama import Fore
import boto3
from botocore.exceptions import ClientError

from components.ui import cprint


class S3:
    def __init__(self, *, region_name, environment_name, service_name, bucket_name, bucket_type):
        self.service_name = service_name
        self.region_name = region_name
        self.environment_name = environment_name
        self._name = bucket_name
        self._bucket_type = bucket_type

        self._s3_client = boto3.client('s3')

    @property
    def name(self):
        return self._name


    def add_lambda_trigger(self, semantic_version, lambda_function):

        lambda_function.add_s3_permission(semantic_version, self)
        lambda_alias_name = self.semantic_version_to_alias_name(semantic_version)
        existing_notification = self._s3_client.get_bucket_notification_configuration(
            Bucket=self.name
            )
        existing_lambda_notifications = existing_notification.get('LambdaFunctionConfigurations', [])
        existing_aliases = [la['LambdaFunctionArn'].split(':')[-1] for la in existing_lambda_notifications]
        try:
            if (
                lambda_alias_name not in existing_aliases and  # does not currently exist
                len(lambda_alias_name.split('_')) == 2 and lambda_alias_name[-1] != '_'):  # only update for new major/minor release not for patch or major_ only
                new_lambda_notification = {
                    'LambdaFunctionArn': f'arn:aws:lambda:{self.region_name}:887689817172:function:{lambda_function._name}:{lambda_alias_name}',
                    'Events': ['s3:ObjectCreated:*'],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'Prefix',
                                    'Value': f'{lambda_alias_name}_lambda_version'
                                },
                            ]
                        }
                    }
                }
                existing_lambda_notifications.append(new_lambda_notification)
                del existing_notification['ResponseMetadata']
                self._s3_client.put_bucket_notification_configuration(
                        Bucket=self.name,
                        NotificationConfiguration={'LambdaFunctionConfigurations': existing_lambda_notifications}
                )
        except ClientError as e:
            if 'ResourceConflictException' in str(e):
                cprint(e, colour=Fore.YELLOW)
                # cprint(f'Permission already exists for /* on {self.name}:{alias_name}', colour=Fore.YELLOW)
            else:
                raise


    @staticmethod
    def semantic_version_to_alias_name(semantic_version):
        return str(semantic_version).replace('.', '_')
