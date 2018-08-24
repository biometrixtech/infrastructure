from colorama import Fore
import boto3

from components.ui import cprint


class LambdaFunction:
    def __init__(self, service, name, s3_filepath):
        self.service = service
        self._name = name.format(ENVIRONMENT=service.environment.name)
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
        self._lambda_client.create_alias(
            FunctionName=self._name,
            Name=alias_name,
            FunctionVersion=lambda_version
        )

    def add_apigateway_permission(self, semantic_version, apigateway):
        alias_name = self.semantic_version_to_alias_name(semantic_version)
        self._lambda_client.add_permission(
            FunctionName=self._name,
            StatementId=alias_name,
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=f'arn:aws:execute-api:{self.service.environment.region}:887689817172:{apigateway.id}/*',
            Qualifier=alias_name
        )

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
        s3_filepath = 'lambdas/{}/{}/{}'.format(self.service.name, ref, self._s3_filepath)
        cprint(f'Updating Lambda {self._name} with bundle s3://{s3_filepath}', colour=Fore.CYAN)
        self._lambda_client.update_function_code(
            FunctionName=self._name,
            S3Bucket='biometrix-infrastructure-{}'.format(self.service.environment.region),
            S3Key=s3_filepath,
            Publish=publish_version
        )

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