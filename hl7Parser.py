import os
import json
import logging
import boto3
from hl7apy import parser
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')


def hl7_str_to_dict(s, use_long_name=True):
    """Convert an HL7 string to a dictionary
    :param s: The input HL7 string
    :param use_long_name: Whether or not to user the long names
                          (e.g. "patient_name" instead of "pid_5")
    :returns: A dictionary representation of the HL7 message
    """

    er7_msg = parser.parse_message(s, find_groups=False)
    msg_id = er7_msg.children[0].MESSAGE_CONTROL_ID.value
    logger.info(f'Parsed message {msg_id} to ER7')
    return hl7_message_to_dict(er7_msg, use_long_name=use_long_name)


def hl7_message_to_dict(m, use_long_name=True):
    """Convert an HL7 message to a dictionary
    :param m: The HL7 message as returned by :func:`hl7apy.parser.parse_message`
    :param use_long_name: Whether or not to user the long names
                          (e.g. "patient_name" instead of "pid_5")
    :returns: A dictionary representation of the HL7 message
    """
    if m.children:
        d = {}
        for c in m.children:
            name = str(c.name).upper()
            if use_long_name:
                name = str(c.long_name).upper() if c.long_name else name
            dictified = hl7_message_to_dict(c, use_long_name=use_long_name)
            if name in d:
                if not isinstance(d[name], list):
                    d[name] = [d[name]]
                d[name].append(dictified)
            else:
                d[name] = dictified
        return d
    else:
        return m.to_er7()


def lambda_handler(event, context):
    logger.info('Start')

    # get the staging bucket name from the environment variables
    stg_bucket = os.environ['STAGING_BUCKET']

    # get the raw bucket name and object key from the S3 event
    raw_bucket = event['Records'][0]['s3']['bucket']['name']
    object_key = event['Records'][0]['s3']['object']['key']
    logger.info(f'Reading {object_key} from {raw_bucket}')

    # get the hl7 file
    obj = s3.get_object(Bucket=raw_bucket, Key=object_key)

    # get the hl7 file content
    hl7 = obj['Body'].read().decode('utf-8')
    logger.debug(f'Working on message {hl7}')

    # Convert hl7 message to json
    hl7_dict = hl7_str_to_dict(hl7, use_long_name=True)

    # add json document to staging bucket
    msg_id = hl7_dict["MSH"]["MESSAGE_CONTROL_ID"]["ST"]["ST"]
    key = f'{time.time()}_{msg_id}.json'
    logger.info(f'Writing {key} to {stg_bucket}')
    s3.put_object(Bucket=stg_bucket, Key=key,
                  Body=json.dumps(hl7_dict, sort_keys=True, indent=2, separators=(',', ': ')))
    logger.info(f'Deleting {object_key} from {raw_bucket}')
    s3.delete_object(Bucket=raw_bucket, Key=object_key)

    logger.info('Completed parsing')
