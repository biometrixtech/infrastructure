#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update

import boto3
import argparse
import os
import subprocess
import time

template_local_dir = os.path.abspath('../cloudformation')
template_s3_bucket = 'biometrix-preprocessing-infrastructure'
template_s3_path = 'cloudformation/'


def trigger_codebuild():
    git_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()
    print('Triggering CodeBuild for version "{}"'.format(git_revision))
    codebuild_client = boto3.client('codebuild', region_name=args.region)
    res = codebuild_client.start_build(
        projectName='preprocessing-batchjob',
        sourceVersion=git_revision,
    )
    print('Build {}'.format(res['build']['id']))
    return res['build']['id']


def poll_for_codebuild_finish(build_id):
    codebuild_client = boto3.client('codebuild', region_name=args.region)
    while True:
        build = codebuild_client.batch_get_builds(ids=[build_id])['builds'][0]
        if build['buildStatus'] == 'IN_PROGRESS':
            print('CodeBuild job still running')
            time.sleep(30)
            continue
        elif build['buildStatus'] in ['FAILED', 'TIMED_OUT', 'FAULT', 'STOPPED']:
            raise Exception("CodeBuild build failed!")
        else:
            print('CodeBuild job complete')
            return
    pass


def update_cf_stack():
    print('Updating CloudFormation stack')
    cf_resource = boto3.resource('cloudformation', region_name=args.region)
    stack = cf_resource.Stack('preprocessing-{}'.format(args.environment))

    parameters = []
    for p in stack.parameters or {}:
        if p['ParameterKey'] == 'BatchJobVersion{}'.format(args.job):
            value = p['ParameterValue'].split(':')
            value[-1] = str(int(value[-1]) + 1)
            print('Incrementing {} job version from {} to {}'.format(args.job, p['ParameterValue'], ':'.join(value)))
            parameters.append({'ParameterKey': p['ParameterKey'], 'ParameterValue': ':'.join(value)})
        else:
            parameters.append({'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True})

    stack.update(
        TemplateURL='https://s3.amazonaws.com/biometrix-preprocessing-infrastructure-{region}/cloudformation/environment.template'.format(
            region=args.region,
        ),
        Parameters=parameters,
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    parser.add_argument('job',
                        type=str,
                        help='The job to update',
                        choices=['Downloadandchunk', 'Sessionprocess2', 'Scoring', 'Databaseupload'])
    # parser.add_argument('version',
    #                     type=str,
    #                     help='the Git version to deploy')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        default='us-west-2')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')

    args = parser.parse_args()

    # build_id = trigger_codebuild()
    update_cf_stack()
    # poll_for_codebuild_finish(build_id)

