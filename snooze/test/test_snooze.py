import json
from textwrap import dedent
import types

import boto
import moto
import pytest
import responses
import six
from testfixtures import LogCapture

import snooze
import github_responses


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


class TestConfigParser(object):
    def test_parse_config(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [tdsmith/test_repo]
            github_username: tdsmith
            github_token: deadbeefcafe
            aws_key: key
            aws_secret: secret
            """))
        parsed = snooze.parse_config(str(config))
        assert parsed[0]["repository_name"] == "tdsmith/test_repo"
        assert parsed[0]["github_username"] == "tdsmith"

    def test_parse_config_defaults(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [default]
            github_username: tdsmith
            github_token: deadbeefcafe
            cruft: ignoreme
            [tdsmith/test_repo]
            aws_key: key
            aws_secret: secret
            """))
        parsed = snooze.parse_config(str(config))
        assert parsed[0]["github_username"] == "tdsmith"

    def test_parse_config_raises(self, tmpdir):
        try:
            import configparser
        except ImportError:
            import ConfigParser as configparser
        config = tmpdir.join("config.txt")
        config.write("[tdsmith/test_repo]\ngithub_username: tdsmith\n")
        with pytest.raises(configparser.NoOptionError):
            snooze.parse_config(str(config))


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
            """))
        return snooze.parse_config(str(config))

    @pytest.fixture
    def sqs_conn(self):
        return boto.sqs.connect_to_region("us-west-2")

    @pytest.fixture
    def sns_conn(self):
        return boto.sns.connect_to_region("us-west-2")

    def test_constructor(self, config, sqs_conn, sns_conn):
        assert len(sqs_conn.get_all_queues()) == 0
        assert len(sns_conn.get_all_topics().
                   get("ListTopicsResponse").
                   get("ListTopicsResult").
                   get("Topics")) == 0

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        snooze.RepositoryListener(events=snooze.LISTEN_EVENTS, **config[0])
        assert len(sqs_conn.get_all_queues()) > 0
        assert len(sns_conn.get_all_topics().
                   get("ListTopicsResponse").
                   get("ListTopicsResult").
                   get("Topics")) > 0

    def test_poll(self, config, sqs_conn):
        self._test_poll_was_polled = False

        def my_callback(event, message):
            self._test_poll_was_polled = True

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(
            events=snooze.LISTEN_EVENTS,
            callbacks=[my_callback], **config[0])
        sqs_queue = sqs_conn.get_all_queues()[0]

        message = boto.sqs.message.Message()
        message.set_body('["example message"]')
        print(message.get_body())
        sqs_queue.write(message)
        assert sqs_queue.count() > 0

        repo_listener.poll()
        assert sqs_queue.count() == 0
        assert self._test_poll_was_polled

    def test_bad_message_is_logged(self, config, sqs_conn):
        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(events=snooze.LISTEN_EVENTS, **config[0])
        sqs_queue = sqs_conn.get_all_queues()[0]
        message = boto.sqs.message.Message()
        message.set_body("this isn't a json message at all")
        sqs_queue.write(message)
        with LogCapture() as l:
            repo_listener.poll()
            assert 'ERROR' in str(l)

        def my_callback(event, message):
            raise ValueError("I object!")
        message = boto.sqs.message.Message()
        message.set_body('["example message"]')
        sqs_queue.write(message)
        repo_listener.register_callback(my_callback)
        with LogCapture() as l:
            repo_listener.poll()
            assert 'I object!' in str(l)


class TestGithubWebhookCallback(object):
    @pytest.fixture
    def config(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [baxterthehacker/public-repo]
            github_username: frodo
            github_token: baggins
            aws_key: shire
            aws_secret: precious
            aws_region: us-west-2
            """))
        return snooze.parse_config(str(config))

    @responses.activate
    def test_issue_comment_callback(self, config):
        """Test that a snooze label is removed from issues when a new comment
        is received."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/2")
        snooze.github_callback(config,
                               "issue_comment",
                               json.loads(github_responses.ISSUE_COMMENT))
        assert len(responses.calls) == 1
