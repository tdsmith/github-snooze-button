import json
import logging
from textwrap import dedent
import types

import boto3
import moto
import pytest
import responses
from testfixtures import LogCapture
import six

import snooze

logging.getLogger("botocore").setLevel(logging.INFO)


class MockAPIMetaclass(type):
    """Metaclass which wraps all methods of its instances with decorators
    that redirect SNS and SQS calls to moto and activates responses."""
    def __new__(cls, name, bases, attrs):
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, types.FunctionType):
                attrs[attr_name] = cls.decorate(attr_value)
        return super(MockAPIMetaclass, cls).__new__(cls, name, bases, attrs)

    @classmethod
    def decorate(cls, func):
        return moto.mock_sqs(moto.mock_sns(responses.activate(func)))


@six.add_metaclass(MockAPIMetaclass)
class TestRepositoryListenener(object):
    @pytest.fixture
    def config(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [tdsmith/test_repo]
            github_username: frodo
            github_token: baggins
            aws_key: shire
            aws_secret: precious
            aws_region: us-west-2
            snooze_label: snooze
            """))
        return snooze.parse_config(str(config))

    @pytest.fixture
    def trivial_message(self):
        a = {"key": "value"}
        b = {"Message": json.dumps(a)}
        (b.setdefault("MessageAttributes", {}).
            setdefault("X-Github-Event", {}).
            setdefault("Value", "spam"))
        return json.dumps(b)

    def test_constructor(self, config):
        sqs = boto3.resource("sqs", region_name="us-west-2")
        sns = boto3.resource("sns", region_name="us-west-2")
        assert len(list(sqs.queues.all())) == 0
        assert len(list(sns.topics.all())) == 0

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        snooze.RepositoryListener(events=snooze.LISTEN_EVENTS, **config["tdsmith/test_repo"])
        assert len(list(sqs.queues.all())) > 0
        assert len(list(sns.topics.all())) > 0

    def test_poll(self, config, trivial_message):
        self._test_poll_was_polled = False

        def my_callback(event, message):
            self._test_poll_was_polled = True

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(
            events=snooze.LISTEN_EVENTS,
            callbacks=[my_callback], **config["tdsmith/test_repo"])

        sqs = boto3.resource("sqs", region_name="us-west-2")
        sqs_queue = list(sqs.queues.all())[0]

        sqs_queue.send_message(MessageBody=trivial_message)
        assert int(sqs_queue.attributes["ApproximateNumberOfMessages"]) > 0

        repo_listener.poll()
        sqs_queue.reload()
        assert int(sqs_queue.attributes["ApproximateNumberOfMessages"]) == 0
        assert self._test_poll_was_polled

    def test_bad_message_is_logged(self, config, trivial_message):
        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(
            events=snooze.LISTEN_EVENTS,
            **config["tdsmith/test_repo"])

        sqs = boto3.resource("sqs", region_name="us-west-2")
        sqs_queue = list(sqs.queues.all())[0]
        sqs_queue.send_message(MessageBody="this isn't a json message at all")

        with LogCapture() as l:
            repo_listener.poll()
            assert 'ERROR' in str(l)

        def my_callback(event, message):
            raise ValueError("I object!")
        sqs_queue.send_message(MessageBody=trivial_message)
        repo_listener.register_callback(my_callback)
        with LogCapture() as l:
            repo_listener.poll()
            assert 'I object!' in str(l)
