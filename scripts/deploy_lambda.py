#!/usr/bin/env python
# Zip and upload a Lambda bundle
import shutil
import zipfile

import boto3
import argparse
import os

template_s3_bucket = 'biometrix-infrastructure'
template_s3_path = 'lambdas/'


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=args.region,
    )


def upload_bundle(bundle):
    print('Uploading bundle')
    s3_resource = get_boto3_resource('s3')
    data = open(bundle, 'rb')
    s3_resource.Bucket(args.bucket + '-' + args.region).put_object(Key=template_s3_path + os.path.basename(bundle), Body=data)


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a Lambda bundle to S3')
    parser.add_argument('bundle',
                        type=str,
                        help='the name of a Lambda python file')
    parser.add_argument('--bucket', '-b',
                        type=str,
                        default=template_s3_bucket,
                        help='S3 Bucket')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')

    args = parser.parse_args()

    zip_filename = zip_bundle(args.bundle)
    upload_bundle(zip_filename)

