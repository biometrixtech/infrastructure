#!/usr/bin/env python3
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from colorama import Fore, Style
from datetime import datetime
from subprocess import CalledProcessError
import argparse
import boto3
import json
import os
import re
import subprocess
import sys
import threading
import time

# input() in Python 3, raw_input() in Python 2
try:
    input = raw_input
except NameError:
    pass

# subservice_stack_mapping = {
#     'infrastructure': {
#         'security': 'infrastructure-security',
#     },
#     'plans': {
#         'monitoring': 'plans-{environment}-MonitoringStack',
#     },
#     'preprocessing': {
#         'compute': 'preprocessing-{environment}-ComputeCluster',
#         'ingest': 'preprocessing-{environment}-IngestStack',
#         'monitoring': 'preprocessing-{environment}-MonitoringCluster',
#         'pipeline': 'preprocessing-{environment}-PipelineCluster',
#     },
#     'time': {
#         'fargateecs': 'time-{environment}-FargateStack',
#     }
# }

lambci_builds_table = boto3.resource('dynamodb', region_name='us-east-1').Table('infrastructure-lambci-builds')


class Spinner:
    spinning = False
    delay = 0.25

    @staticmethod
    def spinning_cursor():
        while 1:
            for cursor in '|/-\\':
                yield cursor

    def __init__(self, delay=None):
        self.spinner_generator = self.spinning_cursor()
        if delay and float(delay):
            self.delay = delay

    def spinner_task(self):
        while self.spinning:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write('\b')
            sys.stdout.flush()

    def start(self):
        self.spinning = True
        threading.Thread(target=self.spinner_task).start()

    def stop(self):
        self.spinning = False
        time.sleep(self.delay)


class Environment(object):
    def __init__(self, region, environment):
        self.region = region
        self.name = environment
        self.stack = boto3.resource('cloudformation', region_name=self.region).Stack(self._get_stack_name())

        self._repository = Repository('infrastructure')

    @property
    def repository(self):
        return self._repository

    def update(self, version, config):
        """
        Update a whole environment to a new template
        :param str version:
        :param dict config:
        """
        def format_param(key, value):
            if value is not None:
                return {'ParameterKey': key, 'ParameterValue': value}
            else:
                return {'ParameterKey': key, 'UsePreviousValue': True}

        if version is None:
            cprint(f'Updating stack {self.stack.stack_name}')
            self.stack.update(
                UsePreviousTemplate=True,
                Parameters=[format_param(k, v) for k, v in config.items()],
                Capabilities=['CAPABILITY_NAMED_IAM']
            )
        else:
            template_url = f'https://s3.amazonaws.com/{s3_bucket_name}/cloudformation/infrastructure/{version}/infrastructure-environment.yaml'
            cprint(f'Updating stack {self.stack.stack_name} using template {template_url}')
            self.stack.update(
                TemplateURL=template_url,
                Parameters=[format_param(k, v) for k, v in config.items()],
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

    def get_current_config(self):
        """
        Get the current configuration of the environment
        :return: dict
        """
        return {p['ParameterKey']: p['ParameterValue'] for p in self.stack.parameters or []}

    def get_service(self, service):
        if service not in ['hardware', 'plans', 'preprocessing', 'statsapi', 'time', 'users']:
            raise ValueError('Unrecognised service')
        return Service(self, service)

    def _get_stack_name(self):
        return f'infrastructure-{self.name}'

    def __str__(self):
        return self.name


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


class Repository(object):
    def __init__(self, service):
        self.service = service
        self._git_dir = self._get_git_dir()

    def upload_working_copy(self):
        """
        Upload the resources currently in the working copy to S3 under the '00000000' commit hash
        """
        # TODO
        raise NotImplementedError()

    def get_build_number_for_version(self, version):
        """
        Get the LambCI build number corresponding to a particular version
        :param str version:
        :return: str
        """
        builds = lambci_builds_table.query(
            KeyConditionExpression=Key('project').eq(self.lambci_project_name),
            FilterExpression=Attr('commit').eq(version)
        )['Items']
        if len(builds) == 0:
            raise Exception(f'No build has been started for version {version}.  Have you pushed your changes?')
        elif len(builds) > 1:
            cprint(f'Multiple builds found for version {version}, using most recent', colour=Fore.YELLOW)
            return max([b['buildNum'] for b in builds])
        else:
            return builds[0]['buildNum']

    def get_build_status(self, build_number):
        """
        Check the status of the LambCI build for a given version, by querying the `infrastructure-lambci-builds`
        DynamoDB table.

        :param str build_number: The build_number to check
        :return: str
        """
        builds = lambci_builds_table.query(KeyConditionExpression=Key('project').eq(self.lambci_project_name) & Key('buildNum').eq(build_number))['Items']
        if len(builds) == 0:
            raise Exception('Unrecognised build number')
        else:
            return builds[0]['status']

    def await_build_completion(self, version):
        """
        Wait until the LambCI build for a given git version has completed

        :param str version: The full commit hash of the version to check
        """
        spinner = Spinner()
        try:
            counts = 12
            build_number = self.get_build_number_for_version(version)
            cprint(f'Waiting for CI build completion for {version} (#{build_number}) ', colour=Fore.CYAN, end="")
            spinner.start()

            while counts >= 0:
                build_status = self.get_build_status(build_number)

                if build_status == 'success':
                    cprint("\b \r\nBuild complete                        ", colour=Fore.GREEN)
                    break

                else:
                    counts -= 1
                    time.sleep(5)
                    continue
            else:
                cprint("\b \r\nBuild not completed after 60 seconds                        ", colour=Fore.RED)
                exit(1)

        finally:
            spinner.stop()
            cprint('')

    def parse_ref(self, version):
        """
        Convert a free-form git reference (full or partial commit hash, branch or tag name, or the special string of
        at least eight zeroes) into a full commit hash and type

        :param str version: The git reference to parse
        :return: (str, str)
        """
        if re.match('^0{8,}$', version):
            # All zeroes = working copy
            cprint('Deploying working copy', colour=Fore.YELLOW)
            return '0' * 40, 'head'
        elif re.match('^[0-9a-f]{40}$', version):
            # Already a full commit hash
            try:
                self._execute_git_command(f'git branch --contains {version}')
                return version, 'commit'
            except CalledProcessError:
                raise Exception(f'Commit {version} does not exist')
        else:
            try:
                # Parse the value as a branch name and get the associated git commit hash
                x2 = subprocess.check_output(f'git rev-parse {version}', cwd=self._git_dir, shell=True).decode('utf-8').strip()
                cprint(f"Branch '{version}' has commit hash {x2}", colour=Fore.GREEN)
                return x2, 'branch'
            except CalledProcessError:
                raise Exception('Version must be a 40-hex-digit git hash or valid branch name')

    def update_git_branch(self, branch_name, version):
        """
        Move a branch pointer to a particular commit

        :param str branch_name: The branch to update
        :param str version: The commit hash of the commit to move to
        """
        try:
            self._execute_git_command(f"git update-ref refs/heads/{branch_name} {version}")
            self._execute_git_command(f"git push origin {branch_name} --force")
        except CalledProcessError as e:
            cprint('Could not update git branch references.  Are your SSH keys set up properly?')

    def get_config(self):
        with open(os.path.join(self._git_dir, 'resource_index.json'), 'r') as f:
            config = json.load(f)
            return config

    def _get_git_dir(self):
        try:
            git_repo_name = 'infrastructure' if self.service == 'time' else self.service
            return os.path.realpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), f'../../{git_repo_name}'))
        except KeyError:
            raise Exception(f'No Git repository configured for service {self.service}')

    def _execute_git_command(self, command):
        return subprocess.check_call(command, cwd=self._git_dir, shell=True)

    @property
    def lambci_project_name(self):
        # Capitalisation of Github repositories (which is inconsistent boo hiss) is preserved in the project key here
        repository_name = ucfirst(self.service) if self.service in ['users'] else self.service
        return f'gh/biometrixtech/{repository_name}'


def map_config(old_config):
    """
    Create the new config
    :param dict old_config:
    :return: list
    """
    param_renames = dict([a.split('->') for a in filter(None, args.param_renames.split(','))])
    param_updates = dict([a.split('->') for a in filter(None, args.param_updates.split(','))])

    new_config = {old_key: None for old_key in old_config.keys()}

    # Rename parameters
    for old_key, new_key in param_renames.items():
        if old_key not in new_config:
            raise Exception(f'{old_key} not found in existing config, cannot rename')

        if new_key == '':
            cprint(f'Removing parameter {old_key}')
        else:
            cprint(f'Renaming parameter {old_key} to {new_key}')
            new_config[new_key] = old_config[old_key]

        del new_config[old_key]

    # Set new parameter values
    for key, value in param_updates.items():
        cprint(f'Setting parameter {key} to "{value}"')
        new_config[key] = value

    return new_config


def cprint(*pargs, **kwargs):
    """
    Print a string to the terminal with colour

    :param pargs: args to print()
    :param kwargs: kwargs to print()
    """
    if 'colour' in kwargs:
        print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        print(*pargs, **kwargs)

        print(Style.RESET_ALL, end=end)

    else:
        print(*pargs, **kwargs)


def confirm(question='', count=0):
    reply = str(input(question)).lower().strip()
    if reply[:1] == 'y':
        return True
    if reply[:1] == 'n' or count >= 3:
        return False
    else:
        return confirm('Please type "yes" or "no": ', count + 1)


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

    if args.environment not in ['test']:
        # TODO
        raise NotImplementedError()
    else:
        environment = Environment(args.region, args.environment)
        service = environment.get_service(args.service)

    if args.environment_version != '':
        environment_version = environment.repository.parse_ref(args.environment_version)[0]
    else:
        environment_version = None

    service_version, ref_type = service.repository.parse_ref(args.version)

    # Do the pre-upload of templates to the 00000000 version
    if ref_type == 'head':
        if args.environment != 'dev':
            raise Exception('Working copy can only be deployed to dev')
        service.repository.upload_working_copy()

    # Check that the build we're about to deploy has actually been completed
    service.repository.await_build_completion(service_version)

    if args.subservice:
        if ref_type != 'head':
            raise Exception('Can only update subservice with working copy')
        else:
            # TODO
            raise NotImplementedError()

    else:
        new_config = map_config(environment.get_current_config())

        # Actually update the service
        new_config[ucfirst(args.service) + 'ServiceVersion'] = service_version

        try:
            environment.update(environment_version, new_config)
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
            service.repository.update_git_branch(f'{args.environment}-{args.region}', service_version)

            # Explicitly deploy lambda functions to make sure they update
            service.update_lambda_functions(service_version)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Deploy a new version of a service to an environment')
    parser.add_argument('--region',
                        choices=['us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('environment',
                        choices=['test'],
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
    except Exception as ex:
        cprint(str(ex), colour=Fore.RED)
        raise ex
    else:
        exit(0)