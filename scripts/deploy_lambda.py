#!/usr/bin/env python
# Zip and upload a Lambda bundle
from __future__ import print_function
from colorama import Fore, Back, Style
import __builtin__
import argparse
import boto3
import os
import shutil
import zipfile


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=args.region,
    )


def upload_bundle(bundle):
    s3_bucket = 'biometrix-infrastructure-{}'.format(args.region)
    s3_path = 'lambdas/{}-{}/{}'.format(args.project, args.environment, os.path.basename(bundle))
    s3_resource = get_boto3_resource('s3')
    data = open(bundle, 'rb')
    s3_resource.Bucket(s3_bucket).put_object(Key=s3_path, Body=data)
    print('Uploaded {} to s3://{}/{}'.format(bundle, s3_bucket, s3_path))


def zip_bundle(filename):
    print('Zipping bundle')
    if filename[-3:] == '.py':
        # Zipping one file
        output_filename = filename.replace('.py', '')
        zipfile.ZipFile(output_filename + '.zip', mode='w').write(filename)
    else:
        output_filename = filename
        shutil.make_archive(output_filename, 'zip', filename)
    return output_filename + '.zip'


def print(*pargs, **kwargs):
    if 'colour' in kwargs:
        __builtin__.print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        __builtin__.print(*pargs, **kwargs)

        __builtin__.print(Style.RESET_ALL, end=end)

    else:
        __builtin__.print(*pargs, **kwargs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Zip and upload a Lambda bundle to S3')
    parser.add_argument('bundle',
                        type=str,
                        help='the name of a Lambda python file or directory')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--project', '-p',
                        type=str,
                        choices=[
                            'alerts',
                            'infrastructure',
                            'hardware',
                            'preprocessing',
                            'statsapi',
                            'users',
                        ],
                        help='The project being deployed')
    parser.add_argument('--environment', '-e',
                        type=str,
                        choices=['infra', 'dev', 'qa', 'production'],
                        help='Environment')

    args = parser.parse_args()

    zip_filename = zip_bundle(args.bundle)
    upload_bundle(zip_filename)

