from textwrap import dedent

import pytest

from snooze.config import parse_config


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
        parsed = parse_config(str(config))
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
        parsed = parse_config(str(config))
        assert parsed["tdsmith/test_repo"]["github_username"] == "tdsmith"
        assert parsed["tdsmith/test_repo"]["poll_interval"] == 0
        assert parsed["tdsmith/test_repo"]["ignore_members_of"] is None

    def test_parse_config_raises(self, tmpdir):
        try:
            import configparser
        except ImportError:
            import ConfigParser as configparser
        config = tmpdir.join("config.txt")
        config.write("[tdsmith/test_repo]\ngithub_username: tdsmith\n")
        with pytest.raises(configparser.NoOptionError):
            parse_config(str(config))
