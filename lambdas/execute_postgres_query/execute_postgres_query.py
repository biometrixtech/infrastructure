import psycopg2
import psycopg2.extras
psycopg2.extras.register_uuid()
import uuid
import boto3
import os
import json
from datetime import datetime, date

from aws_xray_sdk.core import xray_recorder, patch_all
patch_all()


@xray_recorder.capture('execute_postgres_query.load_parameters')
def load_parameters(keys, environment):
    """
    Load configuration from SSM
    :param keys: A list of configuration variables
    :param environment: The environment to load config for
    :return: A dictionary of variables to values
    """
    print('Retrieving configuration from SSM')
    ssm_client = boto3.client('ssm')
    response = ssm_client.get_parameters(
        Names=['preprocessing.{}.{}'.format(environment, key.lower()) for key in keys],
        WithDecryption=True
    )
    params = {p['Name'].split('.')[-1].upper(): p['Value'] for p in response['Parameters']}
    return params


@xray_recorder.capture('execute_postgres_query.handler')
def handler(event, _):
    """
    We expect an event with the following structure:
        {
            "Queries": [
                { "Query": <STRING>, "Parameters": <OBJECT> }
             ],
            "Config": {
                "ENVIRONMENT": <STRING>
            }
        }
    And will return:
        {
            "Results": [ <OBJECT> ],
            "Errors": [ <OBJECT> ]
        }
    With one result per query
    :return:
    """
    try:
        environment = event.get('Config', {}).get('ENVIRONMENT')
        if environment != os.environ['ENVIRONMENT']:
            raise Exception("Query attempted for wrong environment")

        connection = get_postgres_connection()
        cursor = connection.cursor()

        results = []
        errors = []
        for query in event.get("Queries", []):
            try:
                cursor.execute(query.get("Query"), query.get("Parameters", {}))
                results.append(cursor.fetchall() if cursor.description is not None else None)
                errors.append(None)
                connection.commit()
            except psycopg2.Error as e:
                print(e)
                results.append(None)
                errors.append(e.pgerror)

        # Dump and reparse to remove any unserialisable values (like datetimes)
        return json.loads(json.dumps({"Results": results, "Errors": errors}, default=json_serial))

    except:
        raise


@xray_recorder.capture('execute_postgres_query.get_postgres_connection')
def get_postgres_connection():
    config = load_parameters(['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'], os.environ['ENVIRONMENT'])
    print("Connecting to '{}'".format(config['DB_HOST']))
    connection_string = "dbname='{name}' user='{user}' host='{host}' password='{password}'".format(
        host=config['DB_HOST'],
        user=config['DB_USER'],
        password=config['DB_PASSWORD'],
        name=config['DB_NAME'],
    )
    connection = psycopg2.connect(
        connection_string,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=5
    )
    return connection


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    else:
        raise TypeError("Type {} not serializable".format(type(obj)))
