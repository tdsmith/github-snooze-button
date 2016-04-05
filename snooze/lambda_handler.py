from __future__ import absolute_import

import json

from snooze.callbacks import github_callback
from snooze.lambda_config import github_auth, snooze_label


def lambda_handler(event, _):
    for record in event['Records']:
        sns_message = record['Sns']
        github_event = sns_message['MessageAttributes']['X-Github-Event']['Value']
        github_message = json.loads(sns_message['Message'])
        github_callback(github_event, github_message, github_auth, snooze_label)
