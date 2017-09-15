#!/usr/bin/env python
from __future__ import print_function
import argparse
import boto3
import requests
import time


def attach_eni(eni_id):
    while True:
        try:
            ec2_client.attach_network_interface(
                NetworkInterfaceId=eni_id,
                InstanceId=instance_id,
                DeviceIndex=1
            )
            break
        except Exception as e:
            print(e)
            time.sleep(10)


def attach_ebs(volume_id):
    while True:
        try:
            instance.attach_volume(
                VolumeId=volume_id,
                Device="/dev/xvdb"
            )
            break
        except Exception as e:
            print(e)
            time.sleep(10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Invoke one or more test files')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        default='us-west-2')
    args = parser.parse_args()

    ec2_resource = boto3.resource('ec2', region_name=args.region)
    ec2_client = boto3.client('ec2', region_name=args.region)

    instance_id = requests.get('http://169.254.169.254/latest/meta-data/instance-id').text
    instance = ec2_resource.Instance(instance_id)

    tags = {tag['Key']: tag['Value'] for tag in instance.tags}
    eni_id = tags.get('InstanceEniId', None)
    volume_id = tags.get('InstanceVolumeId', None)
    asg_name = tags.get('aws:cloudformation:logical-id', '')

    attach_eni(eni_id)
    attach_ebs(volume_id)

    with open('/tmp/aws_asg_name', 'w') as f:
        f.write(asg_name)
