try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import json
import logging
import pprint

try:
    basestring
except NameError:
    basestring = str

import boto.sqs as sqs
import boto.sns as sns
import requests

GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json"}
LISTEN_EVENTS = ["issues",
                 "issue_comment",
                 "pull_request",
                 "pull_request_review_comment",
                 ]
logging.basicConfig(level=logging.DEBUG)


def parse_config(filename):
    """Parses github-snooze-button configuration files.

    Args:
        filename: The name of a file in ConfigParser .ini format, described
            below.

    Returns:
        A list of dictionaries, one dictionary per repository. Default values
        from the [default] section are automatically copied into each
        dictionary; there is no "default" element in the list.

    Example config file:
    [default]
    github_username = tdsmith
    github_token = asdfasdfasdf
    aws_key = keykeykey
    aws_secret = secretsecret

    [tdsmith/test_repository]

    [tdsmith/some_other_repository]
    github_username = something_else
    github_password = jkljkljkljkl

    github_username, github_token, aws_key, and aws_secret must be defined
    for each region. Defining aws_region is optional; it defaults to us-west-2.
    """
    config = []
    defaults = {"aws_region": "us-west-2"}
    string_options = ["github_username", "github_token", "aws_key", "aws_secret", "aws_region"]
    parser = configparser.SafeConfigParser()
    parser.read(filename)
    sections = parser.sections()
    if "default" in sections:
        for option in parser.options("default"):
            if option not in string_options:
                continue
            defaults[option] = parser.get("default", option)
    for section in sections:
        if section == "default":
            continue
        this_section = {"repository_name": section}
        for option in string_options:
            if option in parser.options(section):
                this_section[option] = parser.get(section, option)
            elif option in defaults:
                this_section[option] = defaults[option]
            else:
                raise configparser.NoOptionError(option, section)
        config.append(this_section)
    return config


class RepositoryListener(object):
    """Sets up infrastructure for listening to a Github repository."""

    def __init__(self, repository_name,
                 github_username, github_token,
                 aws_key, aws_secret, aws_region,
                 events, callbacks=None):
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
            callbacks (list<function(Object)>): functions to call
                with a decoded Github JSON payload when a webhook event lands.
                You can register these after instantiation with
                register_callback.
        """
        self.repository_name = repository_name
        self.github_username = github_username
        self.github_token = github_token
        self.aws_key = aws_key
        self.aws_secret = aws_secret
        self.aws_region = aws_region

        # create or reuse sqs queue
        self.sqs_conn = sqs.connect_to_region(
            aws_region,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
        )
        self.sqs_queue = self.sqs_conn.create_queue(
            "snooze:{}".format(self._to_topic(repository_name)))

        # create or reuse sns topic
        sns_conn = sns.connect_to_region(
            aws_region,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
        )
        sns_response = sns_conn.create_topic(self._to_topic(repository_name))
        sns_topic_arn = (sns_response.
                         get("CreateTopicResponse").
                         get("CreateTopicResult").
                         get("TopicArn"))
        # configure sns topic to push to sqs queue
        sns_conn.subscribe_sqs_queue(sns_topic_arn, self.sqs_queue)

        # configure repository to push to the sns topic
        self._github_connect(sns_topic_arn, events)

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
        messages = self.sqs_queue.get_messages(wait_time_seconds=20*wait)
        for message in messages:
            body = message.get_body()
            logging.debug(
                "Queue {} received message: {}".format(
                    self.sqs_queue.name, body))
            try:
                decoded_body = json.loads(body)
            except ValueError:
                logging.error("Queue {} received non-JSON message: {}".format(
                    self.sqs_queue.name, body))
            else:
                for callback in self._callbacks:
                    try:
                        callback(decoded_body)
                    except Exception as e:
                        logging.error(
                            "Queue {} encountered exception {} while "
                            "processing message {}: {}".format(
                                self.sqs_queue.name, e.__class__.__name__,
                                pprint.pformat(decoded_body), str(e)
                            ))
            finally:
                self.sqs_queue.delete_message(message)

    def _github_connect(self, sns_topic_arn, events):
        """Connects a Github repository to a SNS topic.

        Args:
            sns_topic_arn: ARN of an existing SNS topic
            events (list<str> | str): Github webhook events to monitor for
                activity, from https://developer.github.com/webhooks/#events.

        Returns: None
        """
        auth = requests.auth.HTTPBasicAuth(self.github_username, self.github_token)
        if isinstance(events, basestring):
            events = [events]
        payload = {
            "name": "amazonsns",
            "config": {
                "aws_key": self.aws_key,
                "aws_secret": self.aws_secret,
                "sns_topic": sns_topic_arn,
                "sns_region": self.aws_region,
            },
            "events": events,
        }
        r = requests.post(
            "https://api.github.com/repos/{}/hooks".format(self.repository_name),
            data=json.dumps(payload),
            headers=GITHUB_HEADERS,
            auth=auth)
        r.raise_for_status()

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
            callback (function(Object)): function accepting a single argument
                which receives the JSON-decoded webhook body
        """
        self._callbacks.append(callback)


def main():
    # parse config
    # consume update
    pass
