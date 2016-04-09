import json
from textwrap import dedent
import types

import boto3
import logging
import moto
import pytest
import responses
import six
from testfixtures import LogCapture

import snooze
import github_responses

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


class TestConfigParser(object):
    def test_parse_config(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [tdsmith/test_repo]
            github_username: tdsmith
            github_token: deadbeefcafe
            aws_key: key
            aws_secret: secret
            snooze_label: snooze
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
            snooze_label: snooze
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
            snooze_label: snooze
            """))
        return snooze.parse_config(str(config))["baxterthehacker/public-repo"]

    @responses.activate
    def test_issue_comment_callback(self, config):
        """Test that a snooze label is removed from issues when a new comment
        is received."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/2")
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.SNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is True
        assert len(responses.calls) == 1

    @responses.activate
    def test_issue_comment_callback_not_snoozed(self, config):
        """Don't do anything on receiving an unsnoozed message."""
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.UNSNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
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
        r = snooze.github_callback(
            "pull_request",
            json.loads(github_responses.PULL_REQUEST),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
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
        r = snooze.github_callback(
            "pull_request",
            json.loads(github_responses.PULL_REQUEST),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
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
        r = snooze.github_callback(
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
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
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is False
        assert len(responses.calls) == 1

    def test_bad_callback_type_is_logged(self, config):
        with LogCapture() as l:
            snooze.github_callback("foobar", None, None, None)
            assert "WARNING" in str(l)
