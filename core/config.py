"""
Configuration management for CitationConstellation.

Loads configuration from ~/.citation_config.yaml with fallback to sensible defaults.
Supports environment variable substitution in config values.
"""

import os
import re
import yaml
from pathlib import Path

# Default configuration
DEFAULT_CONFIG = {
    'default_source': 'ads',
    'sources': {
        'ads': {
            'api_token': '${ADS_API_TOKEN}',
            'rate_limit_seconds': 1.0,
            'max_retries': 3,
            'backoff_multiplier': 2,
            'max_results': 25
        },
        'openalex': {
            'polite_pool_email': '${OPENALEX_POLITE_POOL_EMAIL}',
            'rate_limit_seconds': 0.1,  # 10 req/sec
            'max_retries': 3,
            'backoff_multiplier': 2,
            'max_results': 25,
            'base_url': 'https://api.openalex.org'
        }
    }
}

CONFIG_PATH = Path.home() / '.citation_config.yaml'

# Cached config
_cached_config = None


def load_config():
    """
    Load configuration from ~/.citation_config.yaml or return defaults.

    Returns:
        dict: Configuration dictionary
    """
    global _cached_config

    if _cached_config is not None:
        return _cached_config

    if not CONFIG_PATH.exists():
        print(f"No config file found at {CONFIG_PATH}, using defaults.")
        print("Run: python main.py --init-config to create one.")
        _cached_config = DEFAULT_CONFIG.copy()
        _cached_config = _expand_env_vars(_cached_config)
        return _cached_config

    try:
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)

        # Validate config
        validate_config(config)

        # Expand environment variables
        config = _expand_env_vars(config)

        _cached_config = config
        return config

    except Exception as e:
        print(f"Error loading config from {CONFIG_PATH}: {e}")
        print("Using default configuration.")
        _cached_config = DEFAULT_CONFIG.copy()
        _cached_config = _expand_env_vars(_cached_config)
        return _cached_config


def create_default_config():
    """
    Create a default configuration file at ~/.citation_config.yaml.

    Returns:
        Path: Path to created config file
    """
    if CONFIG_PATH.exists():
        response = input(f"Config file already exists at {CONFIG_PATH}. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Aborting.")
            return CONFIG_PATH

    config_content = """# CitationConstellation Configuration
# Default citation data source: 'ads' or 'openalex'
default_source: ads

# Source-specific settings
sources:
  ads:
    # NASA ADS API token - get from https://ui.adsabs.harvard.edu/
    # You can use environment variable: ${ADS_API_TOKEN}
    api_token: ${ADS_API_TOKEN}
    rate_limit_seconds: 1.0
    max_retries: 3
    backoff_multiplier: 2
    max_results: 25

    openalex:
        # Email for OpenAlex polite pool (required for best performance)
        # You can use environment variable: ${OPENALEX_POLITE_POOL_EMAIL}
        polite_pool_email: ${OPENALEX_POLITE_POOL_EMAIL}
    rate_limit_seconds: 0.1  # 10 requests/second
    max_retries: 3
    backoff_multiplier: 2
    max_results: 25
    base_url: https://api.openalex.org
"""

    try:
        with open(CONFIG_PATH, 'w') as f:
            f.write(config_content)
        print(f"Created default config at: {CONFIG_PATH}")
        print(f"\nIMPORTANT: Edit {CONFIG_PATH} to:")
        print("  1. Set your polite_pool_email for OpenAlex")
        print("  2. Configure your ADS_API_TOKEN if needed")
        return CONFIG_PATH
    except Exception as e:
        print(f"Error creating config file: {e}")
        raise


def get_default_source(config=None):
    """
    Get the configured default citation source.

    Args:
        config: Optional config dict (will load if not provided)

    Returns:
        str: 'ads' or 'openalex'
    """
    if config is None:
        config = load_config()

    return config.get('default_source', 'ads')


def validate_config(config):
    """
    Validate configuration structure and values.

    Args:
        config: Configuration dictionary

    Raises:
        ValueError: If configuration is invalid
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary")

    # Check default_source
    default_source = config.get('default_source')
    if default_source not in ['ads', 'openalex']:
        raise ValueError(f"default_source must be 'ads' or 'openalex', got: {default_source}")

    # Check sources dict exists
    if 'sources' not in config:
        raise ValueError("Config must have 'sources' section")

    sources = config['sources']

    # Validate each source
    for source_name in ['ads', 'openalex']:
        if source_name not in sources:
            raise ValueError(f"Missing source configuration for '{source_name}'")

        source_config = sources[source_name]

        # Check rate_limit_seconds
        rate_limit = source_config.get('rate_limit_seconds')
        if rate_limit is not None and (not isinstance(rate_limit, (int, float)) or rate_limit <= 0):
            raise ValueError(f"{source_name}.rate_limit_seconds must be positive number")

        # Check max_retries
        max_retries = source_config.get('max_retries')
        if max_retries is not None and (not isinstance(max_retries, int) or max_retries < 0):
            raise ValueError(f"{source_name}.max_retries must be non-negative integer")

        # Check backoff_multiplier
        backoff = source_config.get('backoff_multiplier')
        if backoff is not None and (not isinstance(backoff, (int, float)) or backoff < 1):
            raise ValueError(f"{source_name}.backoff_multiplier must be >= 1")

    # Validate OpenAlex email if it's being used
    if default_source == 'openalex' or 'openalex' in sources:
        email = sources['openalex'].get('polite_pool_email', '')
        if not email or email == 'user@example.com':
            print("WARNING: Please set a valid polite_pool_email in your config for OpenAlex.")
        elif not _is_valid_email(email):
            print(f"WARNING: polite_pool_email '{email}' doesn't look like a valid email.")


def _is_valid_email(email):
    """Simple email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def _expand_env_vars(obj):
    """
    Recursively expand environment variables in config values.

    Supports ${VAR_NAME} syntax.

    Args:
        obj: Config object (dict, list, str, or other)

    Returns:
        Object with environment variables expanded
    """
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Match ${VAR_NAME} pattern
        def replace_env_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, '')

        return re.sub(r'\$\{([^}]+)\}', replace_env_var, obj)
    else:
        return obj
