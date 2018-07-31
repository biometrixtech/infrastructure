#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
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

try:
    import builtins as __builtin__
except ImportError:
    import __builtin__

# input() in Python 3, raw_input() in Python 2
try:
    input = raw_input
except NameError:
    pass

subservice_stack_mapping = {
    'infrastructure': {
        'security': 'infrastructure-security',
    },
    'plans': {
        'monitoring': 'plans-{environment}-MonitoringStack',
    },
    'preprocessing': {
        'compute': 'preprocessing-{environment}-ComputeCluster',
        'ingest': 'preprocessing-{environment}-IngestStack',
        'monitoring': 'preprocessing-{environment}-MonitoringCluster',
        'pipeline': 'preprocessing-{environment}-PipelineCluster',
    },
    'time': {
        'fargateecs': 'time-{environment}-FargateStack',
    }
}


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


def get_stack_name():
    cloudformation_client = boto3.client('cloudformation', region_name=args.region)
    res = cloudformation_client.get_paginator('list_stacks').paginate(PaginationConfig={'MaxItems': 99999})
    stacks = [s for page in res for s in page['StackSummaries']]

    if args.subservice == 'environment':
        stack_names = [s['StackName'] for s in stacks
                       if s['StackStatus'] != 'DELETE_COMPLETE'
                       and s['StackName'] == '{}-{}'.format(args.service, args.environment)]
    else:
        stack_prefix = subservice_stack_mapping[args.service][args.subservice].format(environment=args.environment)
        stack_names = [s['StackName'] for s in stacks
                       if s['StackStatus'] != 'DELETE_COMPLETE'
                       and s['StackName'].startswith(stack_prefix)]

    if len(stack_names) == 1:
        return stack_names[0]
    elif len(stack_names) > 1:
        print('Found multiple possible stacks to update! [{}]'.format(', '.join(stack_names)), colour=Fore.RED)
        exit(1)
    else:
        print('Could not find stack to update', colour=Fore.RED)
        exit(1)


def map_parameters(old_parameters):
    param_map = [a.split('->') for a in filter(None, args.param_map.split(','))]
    param_map = dict(param_map)

    parameters = []
    for old_parameter in old_parameters or {}:
        old_parameter_name = old_parameter['ParameterKey']
        if old_parameter_name in param_map:
            if param_map[old_parameter_name] == '':
                print('Removing parameter {}'.format(old_parameter_name))
                continue
            else:
                print('Renaming parameter {} to {}'.format(old_parameter_name, param_map[old_parameter_name]))
                parameters.append({'ParameterKey': param_map[old_parameter_name], 'ParameterValue': old_parameter['ParameterValue']})
        else:
            parameters.append({'ParameterKey': old_parameter_name, 'UsePreviousValue': True})

    return parameters


def update_cf_stack(stack, s3_path):
    print('Updating stack {} using template s3://{}/{}'.format(stack.stack_name, s3_bucket_name, s3_path))
    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{template}'.format(
            region=args.region,
            bucket=s3_bucket_name,
            template=s3_path,
        ),
        Parameters=map_parameters(stack.parameters),
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


def await_stack_update(stack):
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
            stack.reload()
            status = stack.stack_status

            spinner.stop()
            sys.stdout.write("\033[K")  # Clear the line

            if status in fail_statuses:
                print("\rStack status: {}                        ".format(status), colour=Fore.RED)
                failure_resource_statuses = [
                    'UPDATE_ROLLBACK_IN_PROGRESS',
                    'CREATE_FAILED',
                    'UPDATE_FAILED',
                    'DELETE_FAILED'
                ]
                failure_events = [e for e in stack.events.all()
                                  if e.timestamp.replace(tzinfo=None) > cutoff
                                  and e.resource_status in failure_resource_statuses
                                  and e.resource_status_reason is not None]
                print('\n'.join([e.resource_status_reason for e in failure_events]), colour=Fore.RED)
                exit(1)
            elif status in success_statuses:
                print("\rStack status: {}                        ".format(status), colour=Fore.GREEN)
                return
            else:
                print("\rStack status: {} ".format(status), colour=Fore.CYAN, end="")
                spinner.start()
                time.sleep(5)
                continue
    finally:
        spinner.stop()


def await_s3_upload(s3_path):
    spinner = Spinner()
    try:
        s3_client = boto3.client('s3')
        counts = 12
        print('Checking that https://s3.amazonaws.com/{}/{} exists '.format(s3_bucket_name, s3_path), colour=Fore.CYAN, end="")
        spinner.start()

        while counts >= 0:
            s3_files = s3_client.list_objects_v2(Bucket=s3_bucket_name, Prefix=s3_path).get('Contents', [])

            if len(s3_files) == 1 and s3_files[0]['Size'] > 0:
                print("\b \r\nTemplate exists                        ", colour=Fore.GREEN)
                break

            else:
                counts -= 1
                time.sleep(5)
                continue
        else:
            print("\b \r\nTemplate not uploaded after 60 seconds                        ", colour=Fore.RED)
            exit(1)

    finally:
        spinner.stop()
            
            
def update_lambda_functions():
    with open(os.path.join(get_git_dir(), 'resource_index.json'), 'r') as f:
        config = json.load(f)

    lambda_client = boto3.client('lambda', region_name=args.region)
    for lambda_bundle in config['lambdas']:
        lambda_name = lambda_bundle['name'].format(ENVIRONMENT=args.environment)
        s3_filepath = 'lambdas/{}/{}/{}'.format(args.service, args.version, lambda_bundle['s3_filename'])
        print('Updating Lambda {} with bundle s3://{}'.format(lambda_name, s3_filepath))
        lambda_client.update_function_code(FunctionName=lambda_name, S3Bucket=s3_bucket_name, S3Key=s3_filepath)


def update_git_branch(branch_name):
    try:
        git_dir = get_git_dir()
        os.system("git -C {} update-ref refs/heads/{} {}".format(git_dir, branch_name, args.version))
        os.system("git -C {} push origin {} --force".format(git_dir, branch_name))
    except CalledProcessError as e:
        print(e.output, colour=Fore.RED)
        raise


def get_git_dir():
    try:
        git_repo_name = 'infrastructure' if args.service == 'time' else args.service
        return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../{}'.format(git_repo_name)))
    except KeyError:
        return None


def print(*args, **kwargs):
    if 'colour' in kwargs:
        __builtin__.print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        __builtin__.print(*args, **kwargs)

        __builtin__.print(Style.RESET_ALL, end=end)

    else:
        __builtin__.print(*args, **kwargs)


def validate_git_commit(x):
    if re.match('^0{8,}$', x):
        # All zeroes
        print('Deploying working copy', colour=Fore.YELLOW)
        return '0' * 40
    elif re.match('^[0-9a-f]{40}$', x):
        # Git hash
        try:
            subprocess.check_call('git branch --contains {}'.format(x), cwd=get_git_dir(), shell=True)
        except CalledProcessError:
            print('Commit {} does not exist'.format(x), colour=Fore.RED)
            exit(1)
        return x
    else:
        try:
            # Parse the value as a branch name and get the associated git commit hash
            x2 = subprocess.check_output('git rev-parse {}'.format(x), cwd=get_git_dir(), shell=True).decode('utf-8').strip()
            print("Branch '{}' has commit hash {}".format(x, x2), colour=Fore.GREEN)
            return x2
        except CalledProcessError:
            print('Version must be a 40-hex-digit git hash or valid branch name', colour=Fore.RED)
            exit(1)


def confirm(question='', count=0):
    reply = str(input(question)).lower().strip()
    if reply[:1] == 'y':
        return True
    if reply[:1] == 'n' or count >= 3:
        return False
    else:
        return confirm('Please type "yes" or "no": ', count + 1)


def main():
    boto3.setup_default_session(profile_name=args.profile_name)

    if args.environment == 'production':
        print('Are you sure you want to deploy to production?! (y/n)', colour=Fore.YELLOW)
        if not confirm():
            exit(0)

    templates = map_templates(args.service, args.environment, args.subservice, args.version)

    s3_bucket = boto3.resource('s3').Bucket(s3_bucket_name)
    if args.version == '0' * 40:
        if args.environment != 'dev':
            print('Working copy can only be deployed to dev', colour=Fore.RED)
            exit(1)

        for source, dest in templates:
            s3_bucket.put_object(Key=dest, Body=open(source, 'rb'))
            print('Uploaded template from {} to s3://{}/{}'.format(source, s3_bucket.name, dest), colour=Fore.GREEN)

    else:
        # Check that the CF templates have actually been uploaded
        await_s3_upload(templates[0][1])

    if not args.noupdate:
        stack = boto3.resource('cloudformation', region_name=args.region).Stack(get_stack_name())

        try:
            update_cf_stack(stack, templates[0][1])
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                print('No updates are to be performed', colour=Fore.YELLOW)
            elif 'is in UPDATE_IN_PROGRESS state' in str(e):
                print('Stack is already updating', colour=Fore.YELLOW)
                await_stack_update(stack)
            else:
                print(e, colour=Fore.RED)
            exit(1)

        await_stack_update(stack)

        if args.subservice == 'environment' and args.service != 'time':
            # Update git reference
            print('Updating git reference')
            update_git_branch('{}-{}'.format(args.environment, args.region))
            if args.service == 'preprocessing':
                # We also implicitly deployed a new version of the application here
                update_git_branch('{}-{}-app'.format(args.environment, args.region))

            # Explicitly deploy lambda functions to make sure they update
            update_lambda_functions()

        exit(0)


def map_templates(service, environment, subservice, version):
    if subservice in ['vpc', 'apigateway', 'fargateecs']:
        # These subservices, in any service, are drawn from the infrastructure repo
        return [(
            '/vagrant/Infrastructure/cloudformation/{subservice}.yaml'.format(subservice=subservice),
            'cloudformation/infrastructure-{environment}/{subservice}.yaml'.format(environment=environment, subservice=subservice),
        )]
    else:
        base_paths = {
            'alerts': '/vagrant/alerts/cloudformation',
            'infrastructure': '/vagrant/infrastructure/cloudformation',
            'hardware': '/vagrant/hardware/cloudformation',
            'plans': '/vagrant/plans/cloudformation',
            'preprocessing': '/vagrant/preprocessing/cloudformation',
            'statsapi': '/vagrant/statsapi/cloudformation',
            'time': '/vagrant/infrastructure/cloudformation',
            'users': '/vagrant/users/cloudformation',
        }
        valid_subservices = {
            'alerts': ['pipeline'],
            'infrastructure': ['lambci', 'security'],
            'hardware': [],
            'plans': ['monitoring'],
            'preprocessing': ['compute', 'ingest', 'monitoring', 'pipeline'],
            'statsapi': [],
            'time': ['fargateecs'],
            'users': [],
        }
        if service in valid_subservices:
            if subservice in valid_subservices[service] or subservice == 'environment':
                templates = [(
                    '{basepath}/{service}-{subservice}.yaml'.format(
                        basepath=base_paths[service],
                        service=service,
                        subservice=subservice
                    ),
                    'cloudformation/{repo}/{version}/{service}-{subservice}.yaml'.format(
                        repo='infrastructure' if service == 'time' else service,
                        service=service,
                        version=version,
                        subservice=subservice
                    )
                )]
                if subservice == 'environment' and service != 'infrastructure':
                    # For non-infrastructure services, updating the environment means updating all the child stacks
                    templates += [t for s in valid_subservices[service] for t in map_templates(service, environment, s, version)]
                return templates
            else:
                print('Invalid subservice for service', colour=Fore.RED)
                exit(1)
        else:
                print('Invalid service', colour=Fore.RED)
                exit(1)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    parser.add_argument('--region',
                        choices=['us-east-1', 'us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('service',
                        choices=[
                            'alerts',
                            'infrastructure',
                            'hardware',
                            'plans',
                            'preprocessing',
                            'statsapi',
                            'time',
                            'users',
                        ],
                        help='The service being deployed')
    parser.add_argument('environment',
                        choices=['infra', 'dev', 'qa', 'production'],
                        help='Environment')
    parser.add_argument('--subservice',
                        nargs='?',
                        default='environment',
                        help='Sub-service')
    parser.add_argument('version',
                        help='the version to deploy')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')
    parser.add_argument('--param-map',
                        dest='param_map',
                        default='',
                        help='Parameters to rename ("oldparamname->newparamname,...") or drop ("oldparamname->,...")')
    parser.add_argument('--profile-name',
                        dest='profile_name',
                        default='default',
                        help='boto3 profile to use')

    args = parser.parse_args()
    # Need to post-process the version because validation depends on the args.service value
    args.version = validate_git_commit(args.version)

    s3_bucket_name = 'biometrix-infrastructure-{}'.format(args.region)

    try:
        main()
    except KeyboardInterrupt:
        print('Exiting', colour=Fore.YELLOW)
        exit(1)
