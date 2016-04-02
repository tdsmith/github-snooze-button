try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import json
import logging

import boto.sqs as sqs
import boto.sns as sns
import requests

GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json"}
logging.basicConfig(level=logging.DEBUG)


def parse_config(filename):
    """Example config file:
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
    def __init__(self, repository_name, github_username, github_token, aws_key, aws_secret, aws_region):
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
        self._github_connect(sns_topic_arn)

    def poll(self):
        messages = self.sqs_queue.get_messages()
        for message in messages:
            body = message.get_body()
            logging.debug("Queue {} received message: {}".format(self.sqs_queue.name, body))
            # do some processing
            self.sqs_queue.delete_message(message)

    def _github_connect(self, sns_topic_arn):
        auth = requests.auth.HTTPBasicAuth(self.github_username, self.github_token)
        payload = {
            "name": "amazonsns",
            "config": {
                "aws_key": self.aws_key,
                "aws_secret": self.aws_secret,
                "sns_topic": sns_topic_arn,
                "sns_region": self.aws_region,
            },
            "events": ["issues", "issue_comment"],
        }
        r = requests.post(
            "https://api.github.com/repos/{}/hooks".format(self.repository_name),
            data=json.dumps(payload),
            headers=GITHUB_HEADERS,
            auth=auth)
        r.raise_for_status()

    def _to_topic(self, repository_name):
        return repository_name.replace("/", "__")


def main():
    # parse config
    # consume update
    pass
