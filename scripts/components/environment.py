import boto3
from semver import VersionInfo
import sys
import datetime
import time
from colorama import Fore

from components.ui import cprint, Spinner
from components.repository import Repository
from components.service import Service


class Environment(object):
    def __init__(self, region, environment):
        self.region = region
        self.name = environment

        self._config = None
        self._stack_template_url = None
        self._stack = None

        self._repository = Repository('infrastructure')

    @property
    def repository(self):
        return self._repository

    @property
    def config(self):
        if self._config is None:
            self._config = {p['ParameterKey']: p['ParameterValue'] for p in self.stack.parameters or []}
        return self._config

    @property
    def stack(self):
        if self._stack is None:
            self._stack = boto3.resource('cloudformation', region_name=self.region).Stack(self._get_stack_name())
        return self._stack

    def update_environment_version(self, version):
        if version is not None:
            self._stack_template_url = f'https://s3.amazonaws.com/biometrix-infrastructure-{self.region}/cloudformation/infrastructure/{version}/infrastructure-environment.yaml'

    def update_service_version(self, service, version):
        self.update_config({ucfirst(service) + 'ServiceVersion': version})

    def update(self):
        """
        Commit an update to the Environment
        """
        def format_param(key, value):
            if value is not None:
                return {'ParameterKey': key, 'ParameterValue': value}
            else:
                return {'ParameterKey': key, 'UsePreviousValue': True}

        if self._stack_template_url is None:
            cprint(f'Updating stack {self.stack.stack_name}')
            self.stack.update(
                UsePreviousTemplate=True,
                Parameters=[format_param(k, v) for k, v in self._config.items()],
                Capabilities=['CAPABILITY_NAMED_IAM']
            )
        else:
            template_url = self._stack_template_url
            cprint(f'Updating stack {self.stack.stack_name} using template {template_url}')
            self.stack.update(
                TemplateURL=template_url,
                Parameters=[format_param(k, v) for k, v in self._config.items()],
                Capabilities=['CAPABILITY_NAMED_IAM']
            )

    def await_deployment_complete(self):
        """
        Wait for the environment to be in a deployment-complete state
        """
        fail_statuses = [
            'UPDATE_ROLLBACK_IN_PROGRESS',
            'UPDATE_ROLLBACK_FAILED',
            'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
            'UPDATE_ROLLBACK_COMPLETE'
        ]
        success_statuses = ['UPDATE_COMPLETE', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS']
        cutoff = datetime.datetime.now()

        spinner = Spinner()

        try:
            spinner.start()
            while True:
                self.stack.reload()
                status = self.stack.stack_status

                spinner.stop()
                sys.stdout.write("\033[K")  # Clear the line

                if status in fail_statuses:
                    cprint("\rStack status: {}                        ".format(status), colour=Fore.RED)
                    failure_resource_statuses = [
                        'UPDATE_ROLLBACK_IN_PROGRESS',
                        'CREATE_FAILED',
                        'UPDATE_FAILED',
                        'DELETE_FAILED'
                    ]
                    failure_events = [e for e in self.stack.events.all()
                                      if e.timestamp.replace(tzinfo=None) > cutoff
                                      and e.resource_status in failure_resource_statuses
                                      and e.resource_status_reason is not None]
                    cprint('\n'.join([e.resource_status_reason for e in failure_events]), colour=Fore.RED)
                    exit(1)
                elif status in success_statuses:
                    cprint("\rStack status: {}                        ".format(status), colour=Fore.GREEN)
                    return
                else:
                    cprint("\rStack status: {} ".format(status), colour=Fore.CYAN, end="")
                    spinner.start()
                    time.sleep(5)
                    continue
        finally:
            spinner.stop()

    def update_config(self, new_config):
        """
        Apply new config
        :param dict new_config:
        :return:
        """
        for key, value in new_config.items():
            if value is None:
                continue
            elif value is NotImplemented:
                del self._config[key]
            else:
                self._config[key] = value

    def _get_service(self, service):
        if service not in ['hardware', 'plans', 'preprocessing', 'statsapi', 'time', 'users']:
            raise ValueError('Unrecognised service')
        return Service(self, service)

    def get_service_repository(self, service):
        return self._get_service(service).repository

    def update_lambda_functions(self, service, ref, tag=None):
        service = self._get_service(service)
        service.update_lambda_functions(ref, tag is not None)
        if tag is not None:
            service.create_lambda_aliases(tag)

    def update_sliding_lambda_aliases(self, service, semantic_version: VersionInfo):
        service = self._get_service(service)
        if semantic_version.patch != 0:
            # New patch version --> slide both major and minor
            service.update_lambda_aliases(f'{semantic_version.major}.{semantic_version.minor}', semantic_version)
            service.update_lambda_aliases(f'{semantic_version.major}_', semantic_version)
        elif semantic_version.patch == 0 and semantic_version.minor != 0:
            # New minor version --> slide major, new minor
            service.create_lambda_aliases(f'{semantic_version.major}.{semantic_version.minor}', semantic_version)
            service.create_apigateway_stages(f'{semantic_version.major}.{semantic_version.minor}')
            service.update_lambda_aliases(f'{semantic_version.major}_', semantic_version)
        else:
            # New major version
            service.create_lambda_aliases(f'{semantic_version.major}.{semantic_version.minor}', semantic_version)
            service.create_apigateway_stages(f'{semantic_version.major}.{semantic_version.minor}')
            service.create_lambda_aliases(f'{semantic_version.major}_', semantic_version)
            service.create_apigateway_stages(f'{semantic_version.major}_')

    def create_apigateway_stages(self, service, tag):
        self._get_service(service).create_apigateway_stages(tag=tag)

    def _get_stack_name(self):
        return f'infrastructure-{self.name}'

    def __str__(self):
        return self.name


class LegacyEnvironment(Environment):
    def __init__(self, region, environment, service):
        super().__init__(region, environment)
        self._service = super()._get_service(service)
        self._repository = self._service.repository

    def _get_service(self, service):
        if service != self._service.name:
            raise ValueError('Legacy environments only support updating services homogeneously')
        return self._service

    def _get_stack_name(self):
        return f'{self._service.name}-{self.name}'

    def update_service_version(self, service, version):
        self._stack_template_url = f'https://s3.amazonaws.com/biometrix-infrastructure-{self.region}/cloudformation/{self._service.name}/{version}/{self._service.name}-environment.yaml'

    def update_environment_version(self, version):
        # Noop
        pass


def ucfirst(s: str) -> str:
    """
    Uppercase the first letter of a string
    :param str s:
    :return: str
    """
    return s[0].upper() + s[1:]
