#
# Copyright 2017 Melon Software Ltd (UK), all rights reserved
#
from botocore.vendored import requests
from functools import partial
import boto3
import json
import logging
import os
import random
import sys
import time
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)
boto3.set_stream_logger('boto')

aws_region = os.environ['AWS_DEFAULT_REGION']


class HandlerException(Exception):
    pass


class ResourceException(Exception):
    pass


class CloudFormationHandler:
    def __init__(self, event, context):
        self.event = event
        self.context = context
        self.resource_type = event.get('ResourceType', None)
        self.action = event.get('RequestType')
        self.physical_resource_id = event.get('PhysicalResourceId', None)

    def _send_cloudformation_response(self, success, response_data=None, reason=None):
        """
        Send a CloudFormation response
        """
        try:
            json_response_body = json.dumps({
                'Status': 'SUCCESS' if success else 'FAILED',
                'Reason': reason or 'See the details in CloudWatch Log Stream: ' + self.context.log_stream_name,
                'PhysicalResourceId': self.physical_resource_id or self.context.log_stream_name,
                'StackId': self.event['StackId'],
                'RequestId': self.event['RequestId'],
                'LogicalResourceId': self.event['LogicalResourceId'],
                'Data': response_data or {}
            }, default=json_serial)
            requests.put(
                self.event['ResponseURL'],
                data=json_response_body,
                headers={'content-type': '', 'content-length': str(len(json_response_body))}
            )
        except Exception as e:
            print("send(..) failed executing requests.put(..): " + str(e))

    def process(self):
        """
        Process a request from CloudFormation
        """
        try:
            # Construct a Resource object
            if self.resource_type == 'Custom::CodeBuildEcrImage':
                resource = CodeBuildEcrImage(self.event)
            elif self.action == 'Delete':
                # Probably rolling back, allow that to happen
                self._send_cloudformation_response(True, reason="Allowing rollback")
                return
            else:
                raise HandlerException("Unknown resource type '{}'".format(self.resource_type))

            # Execute the appropriate action
            if self.action == 'Create':
                self.physical_resource_id = resource.create(self.event['ResourceProperties'])
            elif self.action == 'Update':
                resource.update(
                    self.event['PhysicalResourceId'],
                    self.event['OldResourceProperties'],
                    self.event['ResourceProperties']
                )
            elif self.action == 'Delete':
                resource.delete(self.event['PhysicalResourceId'], self.event['ResourceProperties'])
            else:
                raise HandlerException("Unknown RequestType")
            self._send_cloudformation_response(True)

        except (HandlerException, ResourceException) as e:
            self._send_cloudformation_response(False, reason=str(e))

        except Exception as e:
            raise
            self._send_cloudformation_response(False, reason=str(e) + "\n\n" + traceback.format_exc())


class CodeBuildEcrImage:

    def __init__(self, event):
        self.codebuild_client = boto3.client('codebuild', region_name=aws_region)
        self.ecr_client = boto3.client('ecr', region_name=aws_region)

    class NoSuchImageException(Exception):
        pass

    class CodebuildStillRunningException(Exception):
        pass

    class CodebuildFailedException(Exception):
        pass

    def create(self, properties):
        """
        Check whether the image exists in the ECR repository, if not trigger a CodeBuild job and wait
        for it to complete.
        """
        ecr_registry_name = os.environ['ECR_REGISTRY']
        ecr_repository_name = os.environ['ECR_REPOSITORY']
        ecr_image_tag = properties.get('EcrImageTag', 'latest')

        try:
            ecr_image_digest = self._assert_image_exists(ecr_registry_name, ecr_repository_name, ecr_image_tag)
        except self.NoSuchImageException as e:
            # Need to create it
            print('Triggering CodeBuild for version "{}"'.format(ecr_image_tag))
            res = self.codebuild_client.start_build(
                projectName='preprocessing-batchjob',
                sourceVersion=ecr_image_tag,
            )
            build_id = res['build']['id']
            print('Build {}'.format(build_id))

            # Wait for the image to be created
            self._wait_for_codebuild_completion(
                build_id,
                delay=15,
                tries=20
            )

            ecr_image_digest = self._assert_image_exists(ecr_registry_name, ecr_repository_name, ecr_image_tag)

        return "{}/{}@{}".format(ecr_registry_name, ecr_repository_name, ecr_image_digest)

    def update(self, physical_resource_id, old_properties, new_properties):
        """
        Update properties of the resource
        """
        # Just the same as create
        return self.create(new_properties)

    def delete(self, physical_resource_id, properties):
        """
        Delete the resource
        """
        pass

    def _wait_for_image_to_exist(self, repository_name, image_tag, delay=10, tries=15) -> (bool, str):
        """
        Wait for an image with a given tag to exist in an ECR repository
        """
        return retry_call(
            self._assert_image_exists,
            [repository_name, image_tag],
            exceptions=self.NoSuchImageException,
            tries=tries,
            delay=delay
        )

    def _wait_for_codebuild_completion(self, build_id, delay=10, tries=15) -> (bool, str):
        """
        Wait for a CodeBuild job to complete
        """
        return retry_call(
            self._assert_codebuild_completed,
            [build_id],
            exceptions=self.CodebuildStillRunningException,
            tries=tries,
            delay=delay
        )

    def _assert_image_exists(self, registry_name, repository_name, image_tag) -> str:
        """
        Check whether an image with a given tag exists in an ECR repository, returning its digest
        """
        image_digest = self._get_all_images(registry_name, repository_name).get(image_tag, None)
        if image_digest is None:
            raise self.NoSuchImageException()
        else:
            return image_digest

    def _assert_codebuild_completed(self, build_id) -> bool:
        """
        Assert that a CodeBuild job has finished
        """
        build = self.codebuild_client.batch_get_builds(ids=[build_id])['builds'][0]
        if build['buildStatus'] == 'IN_PROGRESS':
            raise self.CodebuildStillRunningException()
        elif build['buildStatus'] in ['FAILED', 'TIMED_OUT', 'FAULT', 'STOPPED']:
            raise self.CodebuildFailedException("CodeBuild build failed!")
        else:
            print('CodeBuild job complete')
            return True

    def _get_all_images(self, registry_name, repository_name, next_token=None):
        if next_token is None:
            res = self.ecr_client.list_images(repositoryName=repository_name)
        else:
            res = self.ecr_client.list_images(repositoryName=repository_name, nextToken=next_token)
        images = {image['imageTag'] if 'imageTag' in image else 'none': image['imageDigest'] for image in res['imageIds']}
        if 'nextToken' in res:
            images.update(self._get_all_images(registry_name, repository_name, res['nextToken']))
        return images


def handler(event, context):
    logger.info(json.dumps(event, default=json_serial, indent=4))
    cf_handler = CloudFormationHandler(event, context)
    cf_handler.process()


def json_serial(obj):
    """
    JSON serializer for objects not serializable by default json code
    """
    from datetime import datetime
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError("Type not serializable")


def retry_call(f, fargs=None, fkwargs=None, exceptions=Exception, tries=-1, delay=1,
               max_delay=sys.maxsize, backoff=1, jitter=0):
    """
    Calls a function and re-executes it if it failed.
    :param f: the function to execute
    :param fargs: the positional arguments of the function to execute.
    :param fkwargs: the named arguments of the function to execute.
    :param exceptions: an exception or a tuple of exceptions to catch. default: Exception.
    :param tries: the maximum number of attempts. default: -1 (infinite)
    :param delay: initial delay between attempts. default: 1
    :param max_delay: the maximum value of delay. default: None (no limit)
    :param backoff: multiplier applied to delay between attempts. default: 1 (no backoff)
    :param jitter: extra seconds added to delay between attempts. default: 0
                   fixed if a number, random if a range tuple (min, max)
    :returns: the result of the f function
    """
    function_to_call = partial(f, *(fargs if fargs else list()), **(fkwargs if fkwargs else dict()))
    while tries:
        try:
            return function_to_call()
        except exceptions as e:
            tries -= 1
            if tries == 0:
                raise

            logger.warning('%s, retrying in %s seconds...', e, delay)

            time.sleep(delay)
            delay = min(delay * backoff + (random.uniform(*jitter) if isinstance(jitter, tuple) else jitter), max_delay)
