try:
    import configparser
except ImportError:
    import ConfigParser as configparser


def parse_config(filename):
    """Parses github-snooze-button configuration files.

    Args:
        filename: The name of a file in ConfigParser .ini format, described
            below.

    Returns:
        A dictionary of dictionaries, one inner dictionary per repository.
        Default values from the [default] section are automatically copied into
        each dictionary; there is no "default" element in the list.

    Example config file:
    [default]
    github_username = tdsmith
    github_token = asdfasdfasdf
    aws_key = keykeykey
    aws_secret = secretsecret
    poll_interval = 40
    snooze_label = response needed

    [tdsmith/test_repository]

    [tdsmith/some_other_repository]
    github_username = something_else
    github_password = jkljkljkljkl
    snooze_label = snooze

    github_username, github_token, aws_key, aws_secret, and snooze_label must
    be defined for each repository. Defining aws_region is optional; it defaults
    to us-west-2. Defining poll_interval (the time in seconds between 20-second
    long polls) is optional; it defaults to 0.
    """
    config = {}
    defaults = {"aws_region": "us-west-2", "poll_interval": 0}
    string_options = (["github_username", "github_token",
                       "aws_key", "aws_secret", "aws_region",
                       "poll_interval", "snooze_label"])
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
        config.setdefault(section, {}).update(this_section)
    return config
