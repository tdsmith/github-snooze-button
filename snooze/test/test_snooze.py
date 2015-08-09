from textwrap import dedent

import pytest
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
        d = snooze.parse_config(str(config))
        assert hasattr(d, "keys")
        assert "tdsmith/test_repo" in d.keys()
        assert d["tdsmith/test_repo"]["github_username"] == "tdsmith"

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
        d = snooze.parse_config(str(config))
        assert d["tdsmith/test_repo"]["github_username"] == "tdsmith"

    def test_parse_config_raises(self, tmpdir):
        try:
            import configparser
        except ImportError:
            import ConfigParser as configparser
        config = tmpdir.join("config.txt")
        config.write("[tdsmith/test_repo]\ngithub_username: tdsmith\n")
        with pytest.raises(configparser.NoOptionError):
            d = snooze.parse_config(str(config))
