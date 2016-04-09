from __future__ import absolute_import

import json
import logging

from snooze.callbacks import github_callback
from snooze.lambda_config import github_auth, snooze_label

# this appears to be magical
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, _):
    for record in event['Records']:
        sns_message = record['Sns']
        github_event = sns_message['MessageAttributes']['X-Github-Event']['Value']
        logger.debug("Received event type %s" % github_event)
        github_message = json.loads(sns_message['Message'])
        github_callback(github_event, github_message, github_auth, snooze_label)
