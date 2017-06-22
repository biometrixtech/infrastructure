import psycopg2
import psycopg2.extras
import boto3
import os
import json
from datetime import datetime


def load_parameters(keys):
    """
    Load configuration from SSM
    :param keys: A list of configuration variables
    :return: A dictionary of variables to values
    """
    print('Retrieving configuration from SSM')
    ssm_client = boto3.client('ssm', region_name='us-east-1')
    response = ssm_client.get_parameters(
        Names=['preprocessing.{}.{}'.format(os.environ.get('ENVIRONMENT', 'dev'), key.lower()) for key in keys],
        WithDecryption=True
    )
    params = {p['Name'].split('.')[-1].upper(): p['Value'] for p in response['Parameters']}
    return params


def handler(event, context):
    """
    We expect an event with the following structure:
        {
            "Queries": [
                { "Query": <STRING>, "Parameters": <OBJECT> }
             ]
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
        config = load_parameters(['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'])
        connection_string = "dbname='{name}' user='{user}' host='{host}' password='{password}'".format(
            host=config['DB_HOST'],
            user=config['DB_USER'],
            password=config['DB_PASSWORD'],
            name=config['DB_NAME'],
        )
        connection = psycopg2.connect(connection_string, cursor_factory=psycopg2.extras.RealDictCursor)
        cursor = connection.cursor()

        results = []
        errors = []
        for query in event.get("Queries", []):
            try:
                cursor.execute(query.get("Query"), query.get("Parameters", {}))
                results.append(cursor.fetchall())
                errors.append(None)
            except psycopg2.Error as e:
                results.append(None)
                errors.append(e.pgerror)

        # Dump and reparse to remove any unserialisable values (like datetimes)
        return json.loads(json.dumps({"Results": results, "Errors": errors}, default=json_serial))

    except:
        raise


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError("Type not serializable")
