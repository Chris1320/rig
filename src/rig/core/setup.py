from rig.config import runtime_config


def check_if_setup_complete() -> bool:
    """Returns True if the data and configuration
    files are already in their expected locations, False otherwise.
    """

    if not runtime_config.configpath.exists() or not runtime_config.configpath.is_dir():
        return False

    return not (not runtime_config.config_file.exists() or not runtime_config.config_file.is_file())
