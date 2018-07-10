#!/usr/bin/env python

from __future__ import print_function
import boto3
import json
import os
import subprocess
import shutil
import zipfile

aws_regions = ['us-west-2', 'us-east-1']
s3_buckets = {region: boto3.resource('s3').Bucket('biometrix-infrastructure-{}'.format(region)) for region in aws_regions}
default_regions = ['us-west-2']


def replace_in_file(filename, old, new):
    with open(filename, 'r') as f:
        filedata = f.read()
    filedata = filedata.replace(old, new)
    with open(filename, 'w') as f:
        f.write(filedata)


def upload_cf_template(config):
    local_filepath = os.path.realpath(config['src'])
    replace_in_file(local_filepath, 'da39a3ee5e6b4b0d3255bfef95601890afd80709', os.environ['LAMBCI_COMMIT'])
    s3_key = 'cloudformation/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], config['s3_filename'])
    for region in config.get('regions', default_regions):
        print('    Uploading {} to s3://{}/{} '.format(local_filepath, s3_buckets[region].name, s3_key))
        s3_buckets[region].upload_file(local_filepath, s3_key)


def upload_lambda_bundle(config):
    local_filepath = os.path.realpath(config['src'])
    print('Zipping bundle')

    # Zipping one file
    if local_filepath[-3:] == '.py':
        # Write in the version
        replace_in_file(local_filepath, 'da39a3ee5e6b4b0d3255bfef95601890afd80709', os.environ['LAMBCI_COMMIT'])

        output_filename = local_filepath.replace('.py', '.zip')
        zipfile.ZipFile(output_filename + '.zip', mode='w').write(local_filepath)

    # A whole bundle
    else:
        # Install pip requirements first
        if config.get('pip', True):
            subprocess.check_call('python3 -m pip install -t {f} -r {f}/pip_requirements'.format(f=local_filepath), shell=True)

        # Write the version into the bundle
        with open(os.path.join(local_filepath, 'version'), "w") as f:
            f.write(os.environ['LAMBCI_COMMIT'])

        # Now zip
        shutil.make_archive(local_filepath, 'zip', local_filepath)
        output_filename = local_filepath + '.zip'

    s3_key = 'lambdas/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], config['s3_filename'])
    for region in config.get('regions', default_regions):
        print('    Uploading {} to s3://{}/{}'.format(output_filename, s3_buckets[region].name, s3_key))
        s3_buckets[region].upload_file(output_filename, s3_key)


def read_config():
    with open('resource_index.json', 'r') as f:
        return json.load(f)


def main():
    os.environ['PROJECT'] = os.environ['LAMBCI_REPO'].split('/')[-1].lower()
    config = read_config()

    print("Deploying Lambda functions")
    for lambda_config in config['lambdas']:
        upload_lambda_bundle(lambda_config)

    print("Deploying CloudFormation templates")
    for template_config in config['templates']:
        upload_cf_template(template_config)


if __name__ == '__main__':
    main()
