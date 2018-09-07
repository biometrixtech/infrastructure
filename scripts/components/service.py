from components.api_gateway import ApiGateway
from components.lambda_function import LambdaFunction
from components.repository import Repository


class Service(object):
    def __init__(self, environment, service):

        self.environment = environment
        self.name = service

        self._repository = Repository(self.name)

        config = self.repository.get_config()
        self._lambda_functions = [LambdaFunction(
            region_name=self.environment.region,
            service_name=self.name,
            environment_name=self.environment.name,
            function_name=la['name'].format(ENVIRONMENT=self.environment.name),
            s3_filepath=la['s3_filename']
        ) for la in config['lambdas']]
        self._api_gateways = [ApiGateway(ag['name'].format(ENVIRONMENT=self.environment.name), self._get_lambda_function(ag['lambda_function_name'])) for ag in config.get('apigateways', [])]

    @property
    def repository(self) -> Repository:
        return self._repository

    def update_lambda_functions(self, ref, publish_tags=False):
        for lambda_function in self._lambda_functions:
            lambda_function.update_code(ref, publish_tags)

    def create_lambda_aliases(self, tag, from_tag=None):
        """
        Create a new lambda alias
        :param VersionInfo|str tag:
        :param VersionInfo|str from_tag:
        """
        for lambda_function in self._lambda_functions:
            lambda_function.create_alias(tag, from_tag)

    def update_lambda_aliases(self, tag, target_tag):
        for lambda_function in self._lambda_functions:
            lambda_function.update_alias(tag, target_tag)

    def create_apigateway_stages(self, tag):
        for apigateway in self._api_gateways:
            apigateway.create_stage(tag)

    def _get_lambda_function(self, name):
        name = name.format(ENVIRONMENT=self.environment.name)
        for lambda_function in self._lambda_functions:
            if lambda_function.name == name:
                return lambda_function
        raise Exception(f'Could not find lambda function {name}')