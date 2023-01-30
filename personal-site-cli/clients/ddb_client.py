from typing import Any, Dict, List

from boto3 import Session
from boto3.dynamodb.conditions import ConditionBase, Key
from exceptions import DynamoDBException
from mypy_boto3_dynamodb.service_resource import Table
from mypy_boto3_dynamodb.type_defs import PutItemOutputTableTypeDef, QueryOutputTableTypeDef


class Namespaces:
    TRAVEL = "TRAVEL"
    RESUME = "RESUME"
    HOME = "HOME"


class TravelEntities:
    DESTINATION = "DESTINATION"
    PLACE = "PLACE"
    PHOTO = "PHOTO"
    ALBUM = "ALBUM"


class ResumeEntities:
    JOB = "JOB"
    EDUCATION = "EDUCATION"
    SKILL = "SKILL"


class HomeEntities:
    PHOTO = "PHOTO"


class DDBClient:
    PARTITION_KEY = "PK"
    SORT_KEY = "SK"
    ENTITY = "Entity"

    def __init__(self, session: Session, table_name: str):
        self._session = session
        self.table_name = table_name
        self.table: Table = session.resource("dynamodb").Table(table_name)

    def _query_table(self, filtering_exp: ConditionBase) -> List:
        resp: QueryOutputTableTypeDef = self.table.query(KeyConditionExpression=filtering_exp)
        return [item["Entity"] for item in resp["Items"]]

    def _put_item(self, data: Dict[str, Any]) -> None:
        resp: PutItemOutputTableTypeDef = self.table.put_item(Item=data)

        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Put operation failed: {resp}")
        return

    def _delete_item(self, pk: str, sk: str = None) -> None:
        key = {self.PARTITION_KEY: pk}
        if sk:
            key[self.SORT_KEY] = sk

        resp = self.table.delete_item(Key=key)

        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Delete operation failed: {resp}")

        return

    def get_equals(self, partition_key: str, sort_key: str = None) -> List:
        filtering_exp: ConditionBase = Key(self.PARTITION_KEY).eq(partition_key)
        if sort_key:
            filtering_exp = filtering_exp & Key(self.SORT_KEY).eq(sort_key)
        return self._query_table(filtering_exp)

    def get_begins_with(self, partition_key: str, sort_key: str) -> List:
        filtering_exp: ConditionBase = Key(self.PARTITION_KEY).eq(partition_key) & Key(
            self.SORT_KEY
        ).begins_with(sort_key)
        return self._query_table(filtering_exp)

    def put(self, pk: str, sk: str, entity: Dict[str, Any]) -> None:
        data = {self.PARTITION_KEY: pk, self.SORT_KEY: sk, self.ENTITY: entity}
        self._put_item(data)

    def delete(self, pk: str, sk: str) -> None:
        self._delete_item(pk, sk)
