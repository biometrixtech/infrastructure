from colorama import Fore
import boto3
from botocore.exceptions import ClientError

from components.lambda_function import LambdaFunction
from components.ui import cprint


class ApiGateway:
    _id = None

    def __init__(self, name, lambda_function: LambdaFunction):
        self._name = name
        self._lambda_function = lambda_function

        self._apigateway_client = boto3.client('apigateway')

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        if self._id is None:
            for api in self._get_all_rest_apis():
                if api['name'] == self._name:
                    self._id = api['id']
                    break
            else:
                raise Exception(f'API Gateway {self.name} was not found')
        return self._id

    def _get_all_rest_apis(self):
        all_apis = self._apigateway_client.get_rest_apis()
        # TODO paging
        return all_apis['items']

    def get_latest_deployment_id(self):
        all_deployments = self._apigateway_client.get_deployments(restApiId=self.id)['items']
        deployment_id = sorted(all_deployments, key=lambda x: x['createdDate'])[-1]['id']
        return deployment_id

    def create_stage(self, semantic_version):
        deployment_id = self.get_latest_deployment_id()
        stage_name = self.semantic_version_to_stage_name(semantic_version)
        cprint(f'Creating API Gateway stage {self.id}/{deployment_id}/{stage_name} for {self.name}', colour=Fore.CYAN)
        try:
            self._apigateway_client.create_stage(
                restApiId=self.id,
                deploymentId=deployment_id,
                stageName=stage_name,
                variables={'LambdaAlias': LambdaFunction.semantic_version_to_alias_name(semantic_version)}
            )
        except ClientError as e:
            if 'ConflictException' in str(e):
                cprint(f'API Gateway stage {self.id}/{stage_name} already exists', colour=Fore.YELLOW)
            else:
                raise

        self._lambda_function.add_apigateway_permission(semantic_version, self)

    @staticmethod
    def semantic_version_to_stage_name(semantic_version):
        return str(semantic_version).replace('.', '_').rstrip('_')