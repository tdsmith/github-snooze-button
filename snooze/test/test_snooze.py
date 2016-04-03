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
        assert parsed["tdsmith/test_repo"]["repository_name"] == "tdsmith/test_repo"
        assert parsed["tdsmith/test_repo"]["github_username"] == "tdsmith"

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
        assert parsed["tdsmith/test_repo"]["github_username"] == "tdsmith"
        assert parsed["tdsmith/test_repo"]["poll_interval"] == 0

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

    @pytest.fixture
    def trivial_message(self):
        a = {"key": "value"}
        b = {"Message": json.dumps(a)}
        (b.setdefault("MessageAttributes", {}).
            setdefault("X-Github-Event", {}).
            setdefault("Value", "spam"))
        return json.dumps(b)

    def test_constructor(self, config, sqs_conn, sns_conn):
        assert len(sqs_conn.get_all_queues()) == 0
        assert len(sns_conn.get_all_topics().
                   get("ListTopicsResponse").
                   get("ListTopicsResult").
                   get("Topics")) == 0

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        snooze.RepositoryListener(events=snooze.LISTEN_EVENTS, **config["tdsmith/test_repo"])
        assert len(sqs_conn.get_all_queues()) > 0
        assert len(sns_conn.get_all_topics().
                   get("ListTopicsResponse").
                   get("ListTopicsResult").
                   get("Topics")) > 0

    def test_poll(self, config, sqs_conn, trivial_message):
        self._test_poll_was_polled = False

        def my_callback(event, message):
            self._test_poll_was_polled = True

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(
            events=snooze.LISTEN_EVENTS,
            callbacks=[my_callback], **config["tdsmith/test_repo"])
        sqs_queue = sqs_conn.get_all_queues()[0]

        message = boto.sqs.message.Message()
        message.set_body(trivial_message)
        sqs_queue.write(message)
        assert sqs_queue.count() > 0

        repo_listener.poll()
        assert sqs_queue.count() == 0
        assert self._test_poll_was_polled

    def test_bad_message_is_logged(self, config, sqs_conn, trivial_message):
        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(
            events=snooze.LISTEN_EVENTS,
            **config["tdsmith/test_repo"])
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
        message.set_body(trivial_message)
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
        r = snooze.github_callback(config,
                                   "issue_comment",
                                   json.loads(github_responses.SNOOZED_ISSUE_COMMENT))
        assert r is True
        assert len(responses.calls) == 1

    @responses.activate
    def test_issue_comment_callback_not_snoozed(self, config):
        """Don't do anything on receiving an unsnoozed message."""
        r = snooze.github_callback(config,
                                   "issue_comment",
                                   json.loads(github_responses.UNSNOOZED_ISSUE_COMMENT))
        assert r is False
        assert len(responses.calls) == 0

    @responses.activate
    def test_pr_synchronize_callback(self, config):
        """Test that a snooze label is removed from PRs when a new commit is
        pushed."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/octocat/Hello-World/issues/1347")
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.SNOOZED_ISSUE_GET)
        r = snooze.github_callback(config,
                                   "pull_request",
                                   json.loads(github_responses.PULL_REQUEST))
        assert r is True
        assert len(responses.calls) == 2

    @responses.activate
    def test_pr_synchronize_callback_not_snoozed(self, config):
        """Test that a snooze label is not removed from PRs when a new commit is
        pushed but there is no snooze label."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.UNSNOOZED_ISSUE_GET)
        r = snooze.github_callback(config,
                                   "pull_request",
                                   json.loads(github_responses.PULL_REQUEST))
        assert r is False
        assert len(responses.calls) == 1

    @responses.activate
    def test_pr_commit_comment_callback(self, config):
        """Test that a snooze label is removed from PRs when a new commit is
        pushed."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/octocat/Hello-World/issues/1347")
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.SNOOZED_ISSUE_GET)
        r = snooze.github_callback(config,
                                   "pull_request_review_comment",
                                   json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT))
        assert r is True
        assert len(responses.calls) == 2

    @responses.activate
    def test_pr_commit_comment_callback_not_snoozed(self, config):
        """Test that a snooze label is not removed from PRs when a new commit is
        pushed but there is no snooze label."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.UNSNOOZED_ISSUE_GET)
        r = snooze.github_callback(
            config,
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT))
        assert r is False
        assert len(responses.calls) == 1

    def test_bad_callback_type_is_logged(self, config):
        with LogCapture() as l:
            snooze.github_callback(config, "foobar", {})
            assert "WARNING" in str(l)
