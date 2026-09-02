class PersonalSiteCLIException(Exception):
    """The base exception for the PersonalSiteCLI Package"""


class InvalidStateException(PersonalSiteCLIException):
    """Raised when the state of the database is invalid"""


class DynamoDBException(PersonalSiteCLIException):
    """Raised when a DynamoDB operation fails"""


class ConfigException(PersonalSiteCLIException):
    """Raised when the CLI configuration is missing or invalid"""


class ImmichException(PersonalSiteCLIException):
    """Raised when an Immich API operation fails"""
