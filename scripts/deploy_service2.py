#!/usr/bin/env python3
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
from colorama import Fore
from datetime import datetime
import argparse
import boto3
import sys
import time

from components.exceptions import ApplicationException
from components.repository import Repository
from components.ui import confirm, cprint, Spinner


class Environment(object):
    def __init__(self, region, environment):
        self.region = region
        self.name = environment

        self.stack = boto3.resource('cloudformation', region_name=self.region).Stack(self._get_stack_name())
        self._config = {p['ParameterKey']: p['ParameterValue'] for p in self.stack.parameters or []}
        self._stack_template_url = None

        self._repository = Repository('infrastructure')

    @property
    def repository(self):
        return self._repository

    @property
    def config(self):
        return self._config

    def update_environment_version(self, version):
        if version is not None:
            self._stack_template_url = f'https://s3.amazonaws.com/{s3_bucket_name}/cloudformation/infrastructure/{version}/infrastructure-environment.yaml'

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
        cutoff = datetime.now()

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

    def update_lambda_functions(self, service, service_version):
        self._get_service(service).update_lambda_functions(service_version)

    def _get_stack_name(self):
        return f'infrastructure-{self.name}'

    def __str__(self):
        return self.name


class LegacyEnvironment(Environment):
    def __init__(self, region, environment, service):
        self._service = super()._get_service(service)
        super().__init__(region, environment)
        self._repository = self._service.repository

    def _get_service(self, service):
        if service != self._service.name:
            raise ValueError('Legacy environments only support updating services homogeneously')
        return self._service

    def _get_stack_name(self):
        return f'{self._service.name}-{self.name}'

    def update_service_version(self, service, version):
        self._stack_template_url = f'https://s3.amazonaws.com/{s3_bucket_name}/cloudformation/{self._service.name}/{version}/{self._service.name}-environment.yaml'

    def update_environment_version(self, version):
        # Noop
        pass


class Service(object):
    def __init__(self, environment, service):

        self.environment = environment
        self.name = service

        self._repository = Repository(self.name)

    @property
    def repository(self):
        return self._repository

    def update_lambda_functions(self, version):
        config = self.repository.get_config()

        lambda_client = boto3.client('lambda', region_name=self.environment.region)
        for lambda_bundle in config['lambdas']:
            lambda_name = lambda_bundle['name'].format(ENVIRONMENT=self.environment.name)
            s3_filepath = 'lambdas/{}/{}/{}'.format(self.name, version, lambda_bundle['s3_filename'])
            cprint(f'Updating Lambda {lambda_name} with bundle s3://{s3_filepath}')
            lambda_client.update_function_code(FunctionName=lambda_name, S3Bucket=s3_bucket_name, S3Key=s3_filepath)


def map_config(old_config):
    """
    Create the new config
    :param dict old_config:
    :return: list
    """
    param_renames = dict([a.split('->') for a in filter(None, args.param_renames.split(','))])
    param_updates = dict([a.split('->') for a in filter(None, args.param_updates.split(','))])

    new_config = {}

    # Rename parameters
    for old_key, new_key in param_renames.items():
        if old_key not in old_config:
            raise ApplicationException(f'{old_key} not found in existing config, cannot rename')

        if new_key == '':
            cprint(f'Removing parameter {old_key}')
        else:
            cprint(f'Renaming parameter {old_key} to {new_key}')
            new_config[new_key] = old_config[old_key]

        new_config[old_key] = NotImplemented

    # Set new parameter values
    for key, value in param_updates.items():
        cprint(f'Setting parameter {key} to "{value}"')
        new_config[key] = value

    return new_config


def ucfirst(s: str) -> str:
    """
    Uppercase the first letter of a string
    :param str s:
    :return: str
    """
    return s[0].upper() + s[1:]


def main():
    boto3.setup_default_session(profile_name=args.profile_name)

    if args.environment == 'production':
        cprint('Are you sure you want to deploy to production?! (y/n)', colour=Fore.YELLOW)
        if not confirm():
            exit(0)

    if args.environment in ['dev', 'production']:
        environment = LegacyEnvironment(args.region, args.environment, args.service)
        service_repository = environment.get_service_repository(args.service)

        if args.environment_version != '':
            raise ApplicationException('--environment_version parameter is not compatible with legacy environments')
        environment_version = None

    else:
        environment = Environment(args.region, args.environment)
        service_repository = environment.get_service_repository(args.service)
        if args.environment_version != '':
            environment_version = environment.repository.parse_ref(args.environment_version)[0]
            # Check that the build we're about to deploy has actually been completed
            environment.repository.await_build_completion(environment_version)
        else:
            environment_version = None

    service_version, ref_type = service_repository.parse_ref(args.version)

    # Do the pre-upload of templates to the 00000000 version
    if ref_type == 'head':
        if args.environment != 'dev':
            raise ApplicationException('Working copy can only be deployed to dev')
        service_repository.upload_working_copy()

    elif ref_type == 'branch':
        comparison = service_repository.compare_remote_status(args.version)
        if comparison == -1:
            confirm(f'Branch {args.version} is behind origin/{args.version}.  Are you sure you want to deploy an earlier version?')
        elif comparison == 1:
            raise ApplicationException(f'Branch {args.version} is ahead of origin/{args.version}.  You need to push your changes')

    # Check that the build we're about to deploy has actually been completed
    service_repository.await_build_completion(service_version)

    if args.subservice:
        if ref_type != 'head':
            raise ApplicationException('Can only update subservice with working copy')
        else:
            # TODO
            raise NotImplementedError()

    else:
        try:
            # Actually update the service
            environment.update_config(map_config(environment.config))
            environment.update_environment_version(environment_version)
            environment.update_service_version(args.service, service_version)
            environment.update()
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                cprint('No updates are to be performed', colour=Fore.YELLOW)
            elif 'is in UPDATE_IN_PROGRESS state' in str(e):
                cprint('Stack is already updating', colour=Fore.YELLOW)
                environment.await_deployment_complete()
            else:
                cprint(e, colour=Fore.RED)
            exit(1)

        environment.await_deployment_complete()

        if args.service != 'time':
            # Update git reference
            cprint('Updating git reference')
            service_repository.update_git_branch(f'{args.environment}-{args.region}', service_version)

            # Explicitly deploy lambda functions to make sure they update
            environment.update_lambda_functions(args.service, service_version)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Deploy a new version of a service to an environment')
    parser.add_argument('--region',
                        choices=['us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('environment',
                        choices=['dev', 'test', 'production'],
                        help='Environment')
    parser.add_argument('service',
                        choices=[
                            'hardware',
                            'plans',
                            'preprocessing',
                            'statsapi',
                            'time',
                            'users',
                        ],
                        help='The service being deployed')
    parser.add_argument('version',
                        help='the version of the service to deploy')
    parser.add_argument('--environment-version',
                        dest='environment_version',
                        default='',
                        help='The version of the whole-environment template to deploy')

    parser.add_argument('--subservice',
                        default='',
                        help='The subservice to update')

    parser.add_argument('--param-renames',
                        dest='param_renames',
                        default='',
                        help='Parameters to rename ("oldparamname->newparamname,...") or drop ("oldparamname->,...")')
    parser.add_argument('--param-updates',
                        dest='param_updates',
                        default='',
                        help='Parameters to set new values for ("paramname->newvalue,...")')

    parser.add_argument('--profile-name',
                        dest='profile_name',
                        default='default',
                        help='boto3 profile to use')

    args = parser.parse_args()

    s3_bucket_name = 'biometrix-infrastructure-{}'.format(args.region)

    try:
        main()
    except KeyboardInterrupt:
        cprint('Exiting', colour=Fore.YELLOW)
        exit(1)
    except ApplicationException as ex:
        cprint(str(ex), colour=Fore.RED)
        exit(1)
    except Exception as ex:
        cprint(str(ex), colour=Fore.RED)
        raise ex
    else:
        exit(0)
