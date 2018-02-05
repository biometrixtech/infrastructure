#!/usr/bin/env python
# Initialise a new EFS filesystem
import json

import boto3
import argparse
import time


def register_job_definition(job_name, commands):
    res = batch_client.register_job_definition(
        jobDefinitionName=job_name,
        type="container",
        containerProperties={
            "image": "faisyl/alpine-nfs",
            "vcpus": 1,
            "memory": 128,
            "command": [
                "/bin/sh", "-c",
                " \
                    mkdir /net /net/efs ; \
                    mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=10,retrans=2 efs.internal:/ /net/efs 2>&1 ; \
                    {commands}; \
                ".format(commands=commands)
            ],
            "readonlyRootFilesystem": False,
            "privileged": True
        }
    )
    print("Registered new job definition (revision {})".format(res['revision']))
    return res['jobDefinitionArn']


def get_latest_job_definition(job_name):
    res = batch_client.describe_job_definitions(jobDefinitionName=job_name)
    revisions = sorted([(jd['revision'], jd['jobDefinitionArn']) for jd in res['jobDefinitions']])
    return revisions[-1][1]


def submit_job(job_definition_arn, job_name):
    print("Submitting job")
    res = batch_client.submit_job(
        jobName=job_name,
        jobQueue='preprocessing-{}-compute'.format(args.environment),
        jobDefinition=job_definition_arn,
    )
    print("Job ID: {}".format(res['jobId']))
    return res['jobId']


def await_job(job_id):
    while True:
        job = batch_client.describe_jobs(jobs=[job_id])['jobs'][0]
        print("Job status: {}".format(job['status']))
        if job['status'] in ['FAILED']:
            raise Exception("Job failed!")
        elif job['status'] in ['SUCCEEDED']:
            print('Job complete')
            return
        else:
            print('Job still running')
            time.sleep(15)
            continue
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Initialise a newly-created EFS filesystem')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--no-register',
                        action='store_true',
                        dest='noregister',
                        help='Skip registering a new job definition, use the current latest one')

    args = parser.parse_args()
    batch_client = boto3.client('batch', region_name=args.region)

    if args.noregister:
        initialise_arn = get_latest_job_definition('maintenance-initialiseefs')
        install_arn = get_latest_job_definition('maintenance-downloadmodels')
    else:
        initialise_arn = register_job_definition(
            'maintenance-initialiseefs',
            'mkdir -p /net/efs/preprocessing /net/efs/globalmodels /net/efs/globalscalers'
        )
        install_arn = register_job_definition(
            'maintenance-downloadmodels',
            'aws s3 cp s3://biometrix-globalmodels/dev/grf_model_v2_0.h5 /net/efs/globalmodels/grf_model_v2_0.h5; ' +
            'aws s3 cp s3://biometrix-globalmodels/dev/scaler_model_v2_0.pkl /net/efs/globalscalers/scaler_model_v2_0.pkl ;'
        )
    print('Running job {}'.format(initialise_arn))

    initialise_id = submit_job(initialise_arn, '00000000-0000-0000-0000-maintenance-initialiseefs')
    await_job(initialise_id)
    install_id = submit_job(install_arn, '00000000-0000-0000-0000-maintenance-downloadmodels')
    await_job(install_id)
