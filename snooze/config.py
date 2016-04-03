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
