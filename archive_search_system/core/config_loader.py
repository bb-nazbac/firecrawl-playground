"""
YAML Run Configuration Loader with Validation

Loads and validates run configuration YAML files.
Validates all required fields and provides clear error messages.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass


@dataclass
class SearchConfig:
    """Search configuration parameters"""
    query: str
    cities: List[str]
    results_per_city: int


@dataclass
class RunConfig:
    """Complete run configuration"""
    client: str
    search: SearchConfig
    analysis_spec: str

    # Optional parameters with defaults
    test_mode: Optional[int] = None
    resume: bool = False
    start_from: Optional[str] = None
    max_cost_usd: Optional[float] = None
    concurrency: int = 30
    dry_run: bool = False
    rerun_failures: bool = False
    from_run: Optional[str] = None


class ConfigValidationError(Exception):
    """Raised when config validation fails"""
    pass


class ConfigLoader:
    """Loads and validates YAML run configurations"""

    VALID_START_FROM_VALUES = ["search", "scrape", "classify", "export", "dedupe"]

    def __init__(self, config_dir: Path = None):
        """
        Initialize config loader

        Args:
            config_dir: Directory containing run configs (defaults to configs/runs/)
        """
        if config_dir is None:
            # Default to search_system/configs/runs/
            self.config_dir = Path(__file__).parent.parent / "configs" / "runs"
        else:
            self.config_dir = Path(config_dir)

    def load(self, config_name: str) -> RunConfig:
        """
        Load and validate a run configuration

        Args:
            config_name: Name of config file (with or without .yaml extension)

        Returns:
            Validated RunConfig object

        Raises:
            ConfigValidationError: If validation fails
            FileNotFoundError: If config file doesn't exist
        """
        # Add .yaml extension if not present
        if not config_name.endswith('.yaml'):
            config_name += '.yaml'

        config_path = self.config_dir / config_name

        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Looking in: {self.config_dir}"
            )

        # Load YAML
        with open(config_path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ConfigValidationError(f"Invalid YAML syntax: {e}")

        # Validate and construct RunConfig
        return self._validate_and_construct(data, config_name)

    def _validate_and_construct(self, data: Dict[str, Any], config_name: str) -> RunConfig:
        """
        Validate config data and construct RunConfig object

        Args:
            data: Parsed YAML data
            config_name: Name of config file (for error messages)

        Returns:
            Validated RunConfig object

        Raises:
            ConfigValidationError: If validation fails
        """
        errors = []

        # Validate required top-level fields
        if 'client' not in data:
            errors.append("Missing required field: 'client'")
        elif not isinstance(data['client'], str) or not data['client'].strip():
            errors.append("Field 'client' must be a non-empty string")

        if 'search' not in data:
            errors.append("Missing required field: 'search'")
        elif not isinstance(data['search'], dict):
            errors.append("Field 'search' must be a dictionary")

        if 'analysis_spec' not in data:
            errors.append("Missing required field: 'analysis_spec'")
        elif not isinstance(data['analysis_spec'], str) or not data['analysis_spec'].strip():
            errors.append("Field 'analysis_spec' must be a non-empty string")

        # Validate search configuration
        search_config = None
        if 'search' in data and isinstance(data['search'], dict):
            search_config, search_errors = self._validate_search_config(data['search'])
            errors.extend(search_errors)

        # Validate optional fields
        test_mode = self._validate_test_mode(data.get('test_mode'))
        if test_mode is False:  # False means validation failed
            errors.append("Field 'test_mode' must be a positive integer")
            test_mode = None

        start_from = self._validate_start_from(data.get('start_from'))
        if start_from is False:
            errors.append(
                f"Field 'start_from' must be one of: {', '.join(self.VALID_START_FROM_VALUES)}"
            )
            start_from = None

        max_cost_usd = self._validate_max_cost(data.get('max_cost_usd'))
        if max_cost_usd is False:
            errors.append("Field 'max_cost_usd' must be a positive number")
            max_cost_usd = None

        concurrency = self._validate_concurrency(data.get('concurrency', 30))
        if concurrency is False:
            errors.append("Field 'concurrency' must be a positive integer between 1 and 100")
            concurrency = 30

        # Validate boolean fields
        resume = bool(data.get('resume', False))
        dry_run = bool(data.get('dry_run', False))
        rerun_failures = bool(data.get('rerun_failures', False))

        # Validate from_run if rerun_failures is true
        from_run = data.get('from_run')
        if rerun_failures and not from_run:
            errors.append("Field 'from_run' is required when 'rerun_failures' is true")

        # If there are errors, raise exception with all errors
        if errors:
            error_msg = f"Configuration validation failed for '{config_name}':\n"
            error_msg += "\n".join(f"  - {err}" for err in errors)
            raise ConfigValidationError(error_msg)

        # Construct and return RunConfig
        return RunConfig(
            client=data['client'].strip(),
            search=search_config,
            analysis_spec=data['analysis_spec'].strip(),
            test_mode=test_mode,
            resume=resume,
            start_from=start_from,
            max_cost_usd=max_cost_usd,
            concurrency=concurrency,
            dry_run=dry_run,
            rerun_failures=rerun_failures,
            from_run=from_run
        )

    def _validate_search_config(self, search_data: Dict[str, Any]) -> tuple:
        """
        Validate search configuration

        Returns:
            Tuple of (SearchConfig or None, list of error messages)
        """
        errors = []

        # Validate query
        if 'query' not in search_data:
            errors.append("Missing required field: 'search.query'")
        elif not isinstance(search_data['query'], str) or not search_data['query'].strip():
            errors.append("Field 'search.query' must be a non-empty string")

        # Validate cities
        if 'cities' not in search_data:
            errors.append("Missing required field: 'search.cities'")
        elif not isinstance(search_data['cities'], list):
            errors.append("Field 'search.cities' must be a list")
        elif len(search_data['cities']) == 0:
            errors.append("Field 'search.cities' must contain at least one city")
        elif not all(isinstance(city, str) and city.strip() for city in search_data['cities']):
            errors.append("All cities in 'search.cities' must be non-empty strings")

        # Validate results_per_city
        if 'results_per_city' not in search_data:
            errors.append("Missing required field: 'search.results_per_city'")
        elif not isinstance(search_data['results_per_city'], int):
            errors.append("Field 'search.results_per_city' must be an integer")
        elif search_data['results_per_city'] < 1 or search_data['results_per_city'] > 1000:
            errors.append("Field 'search.results_per_city' must be between 1 and 1000")

        if errors:
            return None, errors

        return SearchConfig(
            query=search_data['query'].strip(),
            cities=[city.strip() for city in search_data['cities']],
            results_per_city=search_data['results_per_city']
        ), []

    def _validate_test_mode(self, value: Any) -> Union[Optional[int], bool]:
        """Validate test_mode field. Returns False if invalid, None if not set, int if valid"""
        if value is None:
            return None
        if not isinstance(value, int) or value < 1:
            return False
        return value

    def _validate_start_from(self, value: Any) -> Union[Optional[str], bool]:
        """Validate start_from field. Returns False if invalid, None if not set, str if valid"""
        if value is None:
            return None
        if not isinstance(value, str) or value not in self.VALID_START_FROM_VALUES:
            return False
        return value

    def _validate_max_cost(self, value: Any) -> Union[Optional[float], bool]:
        """Validate max_cost_usd field. Returns False if invalid, None if not set, float if valid"""
        if value is None:
            return None
        try:
            cost = float(value)
            if cost <= 0:
                return False
            return cost
        except (TypeError, ValueError):
            return False

    def _validate_concurrency(self, value: Any) -> Union[int, bool]:
        """Validate concurrency field. Returns False if invalid, int if valid"""
        if not isinstance(value, int) or value < 1 or value > 100:
            return False
        return value


def load_config(config_name: str, config_dir: Path = None) -> RunConfig:
    """
    Convenience function to load a config

    Args:
        config_name: Name of config file (with or without .yaml extension)
        config_dir: Optional custom config directory

    Returns:
        Validated RunConfig object
    """
    loader = ConfigLoader(config_dir)
    return loader.load(config_name)
