from textwrap import dedent

import boto
import moto
import pytest
import responses

import snooze


class TestSnooze(object):
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

    @moto.mock_sqs
    @moto.mock_sns
    @responses.activate
    def test_constructor(self, config):
        sqs_conn = boto.sqs.connect_to_region("us-west-2")
        sns_conn = boto.sns.connect_to_region("us-west-2")
        assert len(sqs_conn.get_all_queues()) == 0
        assert len(sns_conn.get_all_topics()["ListTopicsResponse"]["ListTopicsResult"]["Topics"]) == 0

        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        snooze.RepositoryListener(**config[0])
        assert len(sqs_conn.get_all_queues()) > 0
        assert len(sns_conn.get_all_topics()["ListTopicsResponse"]["ListTopicsResult"]["Topics"]) > 0

    @moto.mock_sqs
    @moto.mock_sns
    @responses.activate
    def test_poll(self, config):
        responses.add(responses.POST, "https://api.github.com/repos/tdsmith/test_repo/hooks")
        repo_listener = snooze.RepositoryListener(**config[0])
        sqs_conn = boto.sqs.connect_to_region("us-west-2")
        sqs_queue = sqs_conn.get_all_queues()[0]

        message = boto.sqs.message.Message()
        message.set_body("example message")
        sqs_queue.write(message)
        assert sqs_queue.count() > 0

        repo_listener.poll()
        assert sqs_queue.count() == 0
