#!/usr/bin/env python
# Zip and upload a Lambda bundle
import shutil

import boto3
import argparse
import os

aws_region = 'us-east-1'
template_s3_bucket = 'biometrix-preprocessing-infrastructure'
template_s3_path = 'lambdas/'


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=aws_region,
    )


def upload_bundle(bundle, bucket):
    print('Uploading bundle')
    s3_resource = get_boto3_resource('s3')
    data = open(bundle, 'rb')
    s3_resource.Bucket(bucket + '-' + aws_region).put_object(Key=template_s3_path + os.path.basename(bundle), Body=data)


def zip_bundle(filename):
    print('Zipping bundle')
    output_filename = filename.replace('.py', '')
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

    args = parser.parse_args()

    zip_filename = zip_bundle(args.bundle)
    upload_bundle(zip_filename, bucket=args.bucket)

