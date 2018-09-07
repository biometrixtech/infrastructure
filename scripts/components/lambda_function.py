from colorama import Fore
import boto3
from botocore.exceptions import ClientError

from components.ui import cprint


class LambdaFunction:
    def __init__(self, *, region_name, environment_name, service_name, function_name, s3_filepath):
        self.service_name = service_name
        self.region_name = region_name
        self.environment_name = environment_name
        self._name = function_name
        self._s3_filepath = s3_filepath

        self._lambda_client = boto3.client('lambda')

    @property
    def name(self):
        return self._name

    def get_latest_version(self):
        return self._get_all_versions()[-1][1]

    def create_alias(self, semantic_version, lambda_version=None):
        """
        Create a new lambda alias
        :param VersionInfo|str semantic_version:
        :param VersionInfo|str lambda_version:
        :return:
        """
        alias_name = self.semantic_version_to_alias_name(semantic_version)

        if lambda_version is None:
            lambda_version = self.get_latest_version()
        else:
            lambda_version = self._get_version_of_alias(self.semantic_version_to_alias_name(lambda_version))

        cprint(f'Tagging version {self.name}:{lambda_version} as alias {alias_name}', colour=Fore.CYAN)

        try:
            self._lambda_client.create_alias(
                FunctionName=self._name,
                Name=alias_name,
                FunctionVersion=lambda_version
            )
        except ClientError as e:
            if 'ResourceConflictException' in str(e):
                cprint(f'Lambda version {self.name}:{alias_name} already exists, updating', colour=Fore.YELLOW)
                self._lambda_client.update_alias(
                    FunctionName=self._name,
                    Name=alias_name,
                    FunctionVersion=lambda_version
                )
            else:
                raise

    def add_apigateway_permission(self, semantic_version, apigateway):
        alias_name = self.semantic_version_to_alias_name(semantic_version)

        try:
            self._lambda_client.add_permission(
                FunctionName=self._name,
                StatementId=f'{apigateway.id}_{alias_name}',
                Action='lambda:InvokeFunction',
                Principal='apigateway.amazonaws.com',
                SourceArn=f'arn:aws:execute-api:{self.region_name}:887689817172:{apigateway.id}/*',
                Qualifier=alias_name
            )
        except ClientError as e:
            if 'ResourceConflictException' in str(e):
                cprint(f'Permission already exists for {apigateway.id}/* on {self.name}:{alias_name}', colour=Fore.YELLOW)
            else:
                raise

    def update_alias(self, semantic_version, target_alias):
        """
        Update an existing lambda alias to point to another alias
        :param target_alias:
        :param semantic_version:
        :return:
        """
        alias_name = self.semantic_version_to_alias_name(semantic_version)
        target_version = self._get_version_of_alias(self.semantic_version_to_alias_name(target_alias))
        cprint(f'Updating {self.name}:{alias_name} to {target_version}', colour=Fore.CYAN)
        self._lambda_client.update_alias(
            FunctionName=self._name,
            Name=alias_name,
            FunctionVersion=target_version
        )

    def update_code(self, ref, publish_version=False):
        s3_filepath = 'lambdas/{}/{}/{}'.format(self.service_name, ref, self._s3_filepath)
        cprint(f'Updating Lambda {self._name} with bundle s3://{s3_filepath}', colour=Fore.CYAN)
        res = self._lambda_client.update_function_code(
            FunctionName=self._name,
            S3Bucket='biometrix-infrastructure-{}'.format(self.region_name),
            S3Key=s3_filepath,
            Publish=publish_version
        )
        if publish_version:
            cprint(f"Published lambda version {res['Version']}")

    def publish_version(self):
        res = self._lambda_client.publish_version(
            FunctionName=self._name
        )
        return res['Version']

    def _get_version_of_alias(self, alias_name):
        return self._lambda_client.get_function(FunctionName=self._name, Qualifier=alias_name)['Configuration']['Version']

    def _get_all_versions(self, next_marker=None):
        if next_marker is not None:
            res = self._lambda_client.list_versions_by_function(FunctionName=self._name, Marker=next_marker)
        else:
            res = self._lambda_client.list_versions_by_function(FunctionName=self._name)
        ret = [(v['LastModified'], v['Version']) for v in res['Versions'] if v['Version'] != '$LATEST']
        if 'NextMarker' in res:
            ret += self._get_all_versions(res['NextMarker'])
        return sorted(ret)

    @staticmethod
    def semantic_version_to_alias_name(semantic_version):
        return str(semantic_version).replace('.', '_')
