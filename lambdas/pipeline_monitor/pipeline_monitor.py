import boto3
import datetime
import os

cloudwatch_client = boto3.client('cloudwatch')
batch_client = boto3.client('batch')
ec2_client = boto3.client('ec2')


def handler(event, context):
    do_compute_cluster_desired_cpus()
    do_compute_cluster_actual_cpus()
    do_job_queue_jobs()


def do_compute_cluster_desired_cpus():
    batch_environment_data = batch_client.describe_compute_environments(
        computeEnvironments=[os.environ['BATCH_COMPUTE_ENVIRONMENT']],
    )['computeEnvironments'][0]
    desired_vcpus = batch_environment_data['computeResources']['desiredvCpus']
    put_cloudwatch_metric('BatchComputeEnvironmentDesiredCpus', desired_vcpus, 'None', compute_environment=True)


def do_compute_cluster_actual_cpus():
    ec2_reservation_data = ec2_client.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['preprocessing-{}-compute'.format(os.environ['ENVIRONMENT'])]},
            {'Name': 'tag:Management', 'Values': ['managed']}
        ]
    )['Reservations']
    ec2_instance_data = [instance for reservation in ec2_reservation_data for instance in reservation['Instances']]
    instance_counts = {}
    for instance in ec2_instance_data:
        if instance['State']['Name'] != 'running':
            continue
        instance_type = instance['InstanceType']
        if instance_type not in instance_counts:
            instance_counts[instance_type] = 0
        instance_counts[instance_type] += 1
    instance_type_data = {
        'Cpus': {
            "c3.large": 2, "c3.xlarge": 4, "c3.2xlarge": 8, "c3.4xlarge": 16, "c3.8xlarge": 32,
            "c4.large": 2, "c4.xlarge": 4, "c4.2xlarge": 8, "c4.4xlarge": 16, "c4.8xlarge": 36,
            "d2.xlarge": 4, "d2.2xlarge": 8, "d2.4xlarge": 16, "d2.8xlarge": 32,
            "f1.2xlarge": 8, "f1.16xlarge": 64,
            "g2.2xlarge": 8, "g2.8xlarge": 32,
            "i2.xlarge": 4, "i2.2xlarge": 8, "i2.4xlarge": 16, "i2.8xlarge": 32,
            "i3.large": 2, "i3.xlarge": 4, "i3.2xlarge": 8, "i3.4xlarge": 16, "i3.8xlarge": 32, "i3.16xlarge": 64,
            "m3.medium": 1, "m3.large": 2, "m3.xlarge": 4, "m3.2xlarge": 8,
            "m4.large": 2, "m4.xlarge": 4, "m4.2xlarge": 8, "m4.4xlarge": 16, "m4.10xlarge": 40, "m4.16xlarge": 64,
            "p2.xlarge": 4, "p2.8xlarge": 32, "p2.16xlarge": 64,
            "r3.large": 2, "r3.xlarge": 4, "r3.2xlarge": 8, "r3.4xlarge": 16, "r3.8xlarge": 32,
            "r4.large": 2, "r4.xlarge": 4, "r4.2xlarge": 8, "r4.4xlarge": 16, "r4.8xlarge": 32, "r4.16xlarge": 64,
            "x1.16xlarge": 64, "x1.32xlarge": 128,
        }
    }
    actual_cpus = sum({k: v * instance_type_data['Cpus'][k] for k, v in instance_counts.items()}.values())
    put_cloudwatch_metric('BatchComputeEnvironmentActualCpus', actual_cpus, 'None', compute_environment=True)


def do_job_queue_jobs():
    # A generator to list all jobs
    def count_all_jobs(status, token=''):
        jobs = batch_client.list_jobs(
            jobQueue=os.environ['BATCH_JOB_QUEUE'],
            jobStatus=status,
            nextToken=token
        )
        count = len(jobs['jobSummaryList'])
        if 'nextToken' in jobs and jobs['nextToken']:
            count += count_all_jobs(status, jobs['nextToken'])
        return count

    for status in ['SUBMITTED', 'PENDING', 'RUNNABLE', 'STARTING', 'RUNNING', 'SUCCEEDED', 'FAILED']:
        count = count_all_jobs(status)
        put_cloudwatch_metric('BatchJobQueueCount{}'.format(status.title()), count, 'None', job_queue=True)


def put_cloudwatch_metric(metric_name, value, unit, job_queue=False, compute_environment=False):
    try:
        dimensions = [
            {'Name': 'Environment', 'Value': os.environ['ENVIRONMENT']},
        ]

        if job_queue:
            dimensions.append({'Name': 'JobQueue', 'Value': os.environ['BATCH_JOB_QUEUE']})
        if compute_environment:
            dimensions.append({'Name': 'ComputeEnvironment', 'Value': os.environ['BATCH_COMPUTE_ENVIRONMENT']})

        cloudwatch_client.put_metric_data(
            Namespace='Preprocessing',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Dimensions': dimensions,
                    'Timestamp': datetime.datetime.utcnow(),
                    'Value': value,
                    'Unit': unit,
                },
            ]
        )
    except Exception as exception:
        print("Could not put cloudwatch metric")
        print(repr(exception))
        # Continue


def json_serial(obj):
    """
    JSON serializer for objects not serializable by default json code
    """
    from datetime import datetime
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError("Type not serializable")
