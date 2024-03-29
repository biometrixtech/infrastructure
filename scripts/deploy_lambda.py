#!/usr/bin/env python3
# Zip and upload a Lambda bundle
from colorama import Fore
import argparse
import boto3
import os
import shutil
import zipfile

from components.ui import cprint


def update_function(bundle, lambda_function_name):
    s3_bucket, s3_path = get_s3_paths(bundle)
    s3_path += '.zip'
    lambda_function_name = lambda_function_name.format(environment=args.environment)
    cprint('Updating function {} with s3://{}/{}'.format(lambda_function_name, s3_bucket, s3_path), colour=Fore.CYAN)
    boto3.client('lambda', region_name=args.region).update_function_code(
        FunctionName=lambda_function_name,
        S3Bucket=s3_bucket,
        S3Key=s3_path,
        Publish=False,
    )


def upload_bundle(bundle):
    s3_bucket, s3_path = get_s3_paths(bundle)
    cprint('Uploading {} to s3://{}/{}'.format(bundle, s3_bucket, s3_path), colour=Fore.CYAN)
    s3_resource = boto3.resource('s3', region_name=args.region)
    data = open(bundle, 'rb')
    s3_resource.Bucket(s3_bucket).put_object(Key=s3_path, Body=data)


def zip_bundle(filename):
    cprint('Zipping bundle', colour=Fore.CYAN)
    if filename[-3:] == '.py':
        # Zipping one file
        output_filename = filename.replace('.py', '')
        zipfile.ZipFile(output_filename + '.zip', mode='w').write(filename)
    else:
        output_filename = filename
        shutil.make_archive(output_filename, 'zip', filename)
    return output_filename + '.zip'


def map_bundle(service, subservice):
    bundles = {
        ('alerts', 'apigateway'): ('/vagrant/alerts/apigateway', 'alerts-{environment}-apigateway-execute'),
        ('hardware', 'apigateway'): ('/vagrant/hardware/apigateway', 'hardware-{environment}-apigateway-execute'),
        ('plans', 'apigateway'): ('/vagrant/plans/apigateway', 'plans-{environment}-apigateway-execute'),
        ('preprocessing', 'apigateway'): ('/vagrant/preprocessing/apigateway', 'preprocessing-{environment}-apigateway-execute'),
        ('preprocessing', 'sessions_stream'): ('/vagrant/preprocessing/lambdas/sessions_stream', 'preprocessing-{environment}-ingest-sessions-stream'),
        ('statsapi', 'apigateway'): ('/vagrant/statsapi/apigateway', 'statsapi-{environment}-apigateway-execute'),
        ('users', 'apigateway'): ('/vagrant/users/apigateway', 'users-{environment}-apigateway-execute'),
        ('users', 'validateauth'): ('/vagrant/users/lambdas/custom_auth', 'users-{environment}-apigateway-validateauth'),
        ('users', 'serviceauth'): ('/vagrant/users/lambdas/custom_auth', 'users-{environment}-apigateway-serviceauth'),
    }
    if (service, subservice) in bundles:
        return bundles[(service, subservice)]
    else:
        cprint('Unrecognised service/subservice combination', colour=Fore.RED)
        exit(1)


def get_s3_paths(bundle):
    s3_bucket = 'biometrix-infrastructure-{}'.format(args.region)
    s3_path = 'lambdas/{}/{}/{}'.format(args.service, '0' * 40, os.path.basename(bundle))
    return s3_bucket, s3_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Zip and upload a Lambda bundle to S3')
    parser.add_argument('--region',
                        type=str,
                        choices=['us-east-1', 'us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('service',
                        type=str,
                        choices=[
                            'alerts',
                            'infrastructure',
                            'hardware',
                            'plans',
                            'preprocessing',
                            'statsapi',
                            'users',
                        ],
                        help='The service being deployed')
    parser.add_argument('environment',
                        type=str,
                        choices=['infra', 'dev', 'test', 'production'],
                        help='Environment')
    parser.add_argument('subservice',
                        type=str,
                        help='Function to deploy')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating lambda function')

    args = parser.parse_args()

    bundle_filename, function_name = map_bundle(args.service, args.subservice)

    zip_filename = zip_bundle(bundle_filename)
    upload_bundle(zip_filename)

    if not args.noupdate:
        update_function(bundle_filename, function_name)
