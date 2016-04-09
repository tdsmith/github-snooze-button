from __future__ import absolute_import

import json
import pprint
import logging

import boto3
import requests

from snooze.constants import GITHUB_HEADERS

try:
    basestring
except NameError:
    basestring = str


class RepositoryListener(object):
    """Sets up infrastructure for listening to a Github repository."""

    def __init__(self, repository_name,
                 github_username, github_token,
                 aws_key, aws_secret, aws_region,
                 events, callbacks=None, **kwargs):
        """Instantiates a RepositoryListener.
        Additionally:
         * Creates or connects to a AWS SQS queue named for the repository
         * Creates or connects to a AWS SNS topic named for the repository
         * Connects the AWS SNS topic to the AWS SQS queue
         * Configures the Github repository to push hooks to the SNS topic

        Args:
            repository_name (str): name of a Github repository, like
                "tdsmith/homebrew-pypi-poet"
            github_username (str): Github username
            github_token (str): Github authentication token from
                https://github.com/settings/tokens/new with admin:org_hook
                privileges
            aws_key (str): AWS key
            aws_secret (str): AWS secret
            aws_region (str): AWS region (e.g. 'us-west-2')
            events (list<str>): List of Github webhook events to monitor for
                activity, from https://developer.github.com/webhooks/#events.
            callbacks (list<function(str event_type, Object event_payload)>):
                functions to call with a decoded Github JSON payload when a
                webhook event lands. You can register these after instantiation
                with register_callback.
        """
        self.repository_name = repository_name
        self.github_username = github_username
        self.github_token = github_token
        self.aws_key = aws_key
        self.aws_secret = aws_secret
        self.aws_region = aws_region

        # create or reuse sqs queue
        sqs_resource = boto3.resource("sqs", region_name=self.aws_region)
        self.sqs_queue = sqs_resource.create_queue(
            QueueName="snooze__{}".format(self._to_topic(repository_name))
        )

        # create or reuse sns topic
        sns_resource = boto3.resource("sns", region_name=self.aws_region)
        sns_topic = sns_resource.create_topic(
            Name=self._to_topic(repository_name)
        )
        sns_topic.subscribe(
            Protocol='sqs',
            Endpoint=self.sqs_queue.attributes["QueueArn"]
        )

        # configure repository to push to the sns topic
        connect_github_to_sns(aws_key, aws_secret, aws_region,
                              github_username, github_token, repository_name,
                              sns_topic.arn, events)

        # register callbacks
        self._callbacks = []
        if callbacks:
            [self.register_callback(f) for f in callbacks]

    def poll(self, wait=True):
        """Checks for messages from the Github repository.

        Args:
            wait (bool): Use SQS long polling, i.e. wait up to 20 seconds for a
                message to be received before returning an empty list.

        Returns: None
        """
        messages = self.sqs_queue.receive_messages(WaitTimeSeconds=20*wait)
        for message in messages:
            body = message.body
            logging.debug(
                "Queue {} received message: {}".format(
                    self.sqs_queue.url, body))
            try:
                decoded_full_body = json.loads(body)
                decoded_body = json.loads(decoded_full_body["Message"])
                event_type = decoded_full_body["MessageAttributes"]["X-Github-Event"]["Value"]
            except ValueError:
                logging.error("Queue {} received non-JSON message: {}".format(
                    self.sqs_queue.url, body))
            else:
                for callback in self._callbacks:
                    try:
                        callback(event_type, decoded_body)
                    except Exception as e:
                        logging.error(
                            "Queue {} encountered exception {} while "
                            "processing message {}: {}".format(
                                self.sqs_queue.url, e.__class__.__name__,
                                pprint.pformat(decoded_body), str(e)
                            ))
            finally:
                message.delete()

    def _to_topic(self, repository_name):
        """Converts a repository_name to a valid SNS topic name.

        Args:
            repository_name: Name of a Github repository

        Returns: str
        """
        return repository_name.replace("/", "__")

    def register_callback(self, callback):
        """Registers a callback on a webhook received event.

        All callbacks are always called, in the order registered, for all events
        received.

        Args:
            callback (function(str, Object)): function accepting an event_type
                argument with the name of the triggered event and an event_payload
                object with the JSON-decoded payload body
        """
        self._callbacks.append(callback)


def connect_github_to_sns(aws_key, aws_secret, aws_region,
                          github_username, github_token, repository_name,
                          sns_topic_arn, events, **_):
    """Connects a Github repository to a SNS topic.

    Args:
        sns_topic_arn: ARN of an existing SNS topic
        events (list<str> | str): Github webhook events to monitor for
            activity, from https://developer.github.com/webhooks/#events.

    Returns: None
    """
    auth = requests.auth.HTTPBasicAuth(github_username, github_token)
    if isinstance(events, basestring):
        events = [events]
    payload = {
        "name": "amazonsns",
        "config": {
            "aws_key": aws_key,
            "aws_secret": aws_secret,
            "sns_topic": sns_topic_arn,
            "sns_region": aws_region,
        },
        "events": events,
    }
    r = requests.post(
        "https://api.github.com/repos/{}/hooks".format(repository_name),
        data=json.dumps(payload),
        headers=GITHUB_HEADERS,
        auth=auth)
    r.raise_for_status()
