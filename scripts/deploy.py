#!/usr/bin/env python3
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
from colorama import Fore
from datetime import datetime
from semver import VersionInfo
import argparse
import boto3
import sys
import time

from components.api_gateway import ApiGateway
from components.exceptions import ApplicationException
from components.lambda_function import LambdaFunction
from components.repository import Repository
from components.ui import confirm, cprint, Spinner


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
            service.update_lambda_aliases(f'{semantic_version.major}_', semantic_version)
        else:
            # New major version
            service.create_lambda_aliases(f'{semantic_version.major}.{semantic_version.minor}', semantic_version)
            service.create_lambda_aliases(f'{semantic_version.major}_', semantic_version)

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


class Service(object):
    def __init__(self, environment, service):

        self.environment = environment
        self.name = service

        self._repository = Repository(self.name)

        config = self.repository.get_config()
        self._lambda_functions = [LambdaFunction(self, la['name'], la['s3_filename']) for la in config['lambdas']]
        self._api_gateways = [ApiGateway(self, ag['name'], self._get_lambda_function(ag['lambda_function_name'])) for ag in config.get('apigateways', [])]

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


def map_config(old_config):
    """
    Create the new config
    :param dict old_config:
    :return: dict
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


def validate_semver_tag(new_tag, old_tags):
    """
    Check for various version consistency gotchas
    :param VersionInfo new_tag:
    :param list[VersionInfo] old_tags:
    :return:
    """
    for old_tag in old_tags:
        if old_tag == new_tag:
            raise ApplicationException(f'Release {args.service}:{new_tag} already exists. To roll back to a previous version, run [deploy.py {args.environment} {args.service} --ref {new_tag}]')
        elif old_tag > new_tag:
            if old_tag.major != new_tag.major:
                # It's ok to prepare a legacy release
                pass
            elif old_tag.minor != new_tag.minor:
                # It's ok to patch an old minor release when a new minor release exists
                pass
            else:
                raise ApplicationException(f'Cannot release {args.service}:{new_tag} because a later version {old_tag} already exists.')

    # Prevent skipping versions
    previous_tag = get_previous_semver(new_tag)
    for old_tag in old_tags:
        if old_tag > previous_tag:
            break
    else:
        raise ApplicationException(f'Cannot release {args.service}:{new_tag} because it skips (at least) version {previous_tag}.')

    if args.environment == 'production' and new_tag.prerelease is not None:
        raise ApplicationException('Pre-release versions (ie with build suffixes) cannot be deployed to production')


def get_previous_semver(v: VersionInfo) -> VersionInfo:
    """
    Return a semantic version which is definitely less than the target version
    :param VersionInfo v:
    :return: VersionInfo
    """
    if v.build is not None:
        raise Exception(f'Cannot calculate previous version because {v} has a build number')

    if v.prerelease is not None:
        prerelease_parts = v.prerelease.split('.')
        if prerelease_parts[-1].isdigit() and int(prerelease_parts[-1]) > 1:
            return VersionInfo(v.major, v.minor, v.patch, prerelease_parts[0] + '.' + str(int(prerelease_parts[-1]) - 1))

    if v.patch > 0:
        return VersionInfo(v.major, v.minor, v.patch - 1)

    if v.minor > 0:
        return VersionInfo(v.major, v.minor - 1, 0)

    if v.major > 0:
        return VersionInfo(v.major - 1, 0, 0)

    raise Exception(f'Could not calculate a previous version for {v}')


def ucfirst(s: str) -> str:
    """
    Uppercase the first letter of a string
    :param str s:
    :return: str
    """
    return s[0].upper() + s[1:]


def main():

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

    if args.ref is None:
        if args.environment == 'production':
            args.ref = 'master'
        else:
            args.ref = f'{args.environment}-master'

    service_version, ref_type = service_repository.parse_ref(args.ref)

    if args.tag is None:
        if args.environment == 'dev':
            # It's ok to not tag versions in dev
            version = None
        elif ref_type == 'tag':
            # Deploying from a tag, could be a rollback
            version = None
        else:
            raise ApplicationException('Deployments to environments above dev must be tagged')
    else:
        version = VersionInfo.parse(args.tag)
        validate_semver_tag(version, service_repository.get_semver_tags())

    #             | head                  | commit    | branch                  | tag
    #  -----------+-----------------------+-----------+-------------------------+-----
    #  dev        | upload_working_copy() | Ok        | compare_remote_status() | Ok
    #  test       | X                     | confirm() | compare_remote_status() | confirm()
    #  <other>    | X                     | confirm() | compare_remote_status() | confirm()
    #  production | X                     | confirm() | compare_remote_status() | confirm()

    # Do the pre-upload of templates to the 00000000 version
    if ref_type == 'head':
        if args.environment == 'dev':
            service_repository.upload_working_copy()
        else:
            raise ApplicationException('Working copy can only be deployed to dev')

    if ref_type == 'branch':
        comparison = service_repository.compare_remote_status(args.ref)
        if comparison == -1:
            if not confirm(f'Branch {args.version} is behind origin/{args.ref}.  Are you sure you want to deploy an earlier version?'):
                exit(0)
        elif comparison == 1:
            raise ApplicationException(f'Branch {args.ref} is ahead of origin/{args.ref}.  You need to push your changes')

    if version is not None:
        cprint(f"Going to tag commit {service_version[0:16]} (from {ref_type} {args.ref}) as {version} and deploy to {args.environment}", colour=Fore.YELLOW)
    else:
        cprint(f"Going to deploy commit {service_version[0:16]} (from {ref_type} {args.ref}) to {args.environment}", colour=Fore.YELLOW)

    if not args.yes and (args.environment != 'dev' or version is not None):
        if not confirm('Is this what you wanted? '):
            exit(0)

    if args.environment == 'production':
        cprint('Are you sure you want to deploy to production?! (y/n)', colour=Fore.YELLOW)
        if not confirm():
            exit(0)

    if version is not None:
        service_repository.create_semver_tag(version, service_version)

    # Check that the build we're about to deploy has actually been completed
    service_repository.await_build_completion(service_version)

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

    if service_repository.git_repo_name != 'infrastructure':
        # Update git reference
        cprint('Updating git reference')
        service_repository.update_git_branch(f'{args.environment}-{args.region}', service_version)

    if version is not None:
        # Create versions and aliases of lambda functions and set up a stage in API Gateway
        environment.update_lambda_functions(args.service, ref=service_version, tag=version)
        environment.create_apigateway_stages(args.service, version)

        if version.prerelease is None:
            # Deploying a 'proper' build, so 'slide' the partially-pinned aliases up to the new version
            environment.update_sliding_lambda_aliases(args.service, version)

    else:
        # Explicitly deploy lambda functions anyway to make sure the $LATEST version is up to date
        environment.update_lambda_functions(args.service, ref=service_version)


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
                            'meta',
                            'plans',
                            'preprocessing',
                            'statsapi',
                            'time',
                            'users',
                        ],
                        help='The service being deployed')

    parser.add_argument('--ref',
                        help='the branch or commit to deploy from',
                        default=None)

    parser.add_argument('--tag',
                        help='the tag to assign to the deployed version of the service',
                        default=None)

    parser.add_argument('--environment-version',
                        dest='environment_version',
                        default='',
                        help='The version of the whole-environment template to deploy')

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
    parser.add_argument('-y',
                        dest='yes',
                        action='store_true',
                        help='Skip confirmations')

    args = parser.parse_args()

    boto3.setup_default_session(profile_name=args.profile_name, region_name=args.region)

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
