# Upload a cloudformation template to S3, then run a stack update
import pickle
from collections import namedtuple

import boto3
import argparse
import os

aws_region = 'us-east-1'
template_local_dir = os.path.abspath('../cloudformation')
template_s3_bucket = 'biometrix-preprocessing-infrastructure'
template_s3_path = 'cloudformation/'


SessionToken = namedtuple('SessionToken', ['access_key_id', 'secret_access_key', 'session_token'])


def get_sts_session_token(iam_user, mfa_token) -> SessionToken:
    if os.path.isfile('.awstoken.p'):
        print('Unpickling session token')
        session_token = pickle.load(open(".awstoken.p", "rb"))
        return session_token

    sts_client = boto3.client('sts', region_name=aws_region)
    session_token_data = sts_client.get_session_token(
        SerialNumber='arn:aws:iam::532972427115:mfa/{}'.format(iam_user),
        TokenCode=mfa_token
    )['Credentials']

    session_token = SessionToken(
        access_key_id=session_token_data['AccessKeyId'],
        secret_access_key=session_token_data['SecretAccessKey'],
        session_token=session_token_data['SessionToken']
    )

    print('Pickling session token')
    pickle.dump(session_token, open(".awstoken.p", "wb"))

    return session_token


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=aws_region,
        aws_access_key_id=session_token.access_key_id,
        aws_secret_access_key=session_token.secret_access_key,
        aws_session_token=session_token.session_token
    )


def upload_cf_stack(template):
    print('Uploading stack')
    s3_resource = get_boto3_resource('s3')
    data = open("{}/{}".format(template_local_dir, template), 'rb')
    s3_resource.Bucket(template_s3_bucket).put_object(Key=template_s3_path + template, Body=data)


def update_cf_stack(stack_name, template):
    print('Updating CloudFormation stack')
    cf_resource = get_boto3_resource('cloudformation')
    stack = cf_resource.Stack(stack_name)

    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{path}{template}'.format(
            region=aws_region,
            bucket=template_s3_bucket,
            path=template_s3_path,
            template=template
        ),
        Parameters=[{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True} for p in stack.parameters or {}],
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    parser.add_argument('template',
                        type=str,
                        help='the name of a template file')
    parser.add_argument('stack',
                        type=str,
                        nargs='?',
                        default='',
                        help='the name of a CF stack')
    parser.add_argument('--mfatoken', '-t',
                        type=str,
                        default='',
                        help='MFA token value')

    args = parser.parse_args()

    session_token = get_sts_session_token('stephen.poole', args.mfatoken)

    upload_cf_stack(args.template)

    if args.stack != '':
        update_cf_stack(args.stack, args.template)

