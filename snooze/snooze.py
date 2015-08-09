try:
    import configparser
except ImportError:
    import ConfigParser as configparser

def parse_config(filename):
    """Example config file:
    [default]
    github_username = tdsmith
    github_token = asdfasdfasdf
    [tdsmith/test_repository]
    [tdsmith/some_other_repository]
    """
    config = {}
    defaults = {}
    string_options = ["github_username", "github_token"]
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
        config[section] = {}
        for option in string_options:
            if option in parser.options(section):
                config[section][option] = parser.get(section, option)
            elif option in defaults:
                config[section][option] = defaults[option]
            else:
                raise configparser.NoOptionError(option, section)
    return config
