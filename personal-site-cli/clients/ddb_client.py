import boto3
from boto3.dynamodb.conditions import Key


class Namespaces:
    TRAVEL = "TRAVEL"
    RESUME = "RESUME"


class TravelEntities:
    DESTINATION = "DESTINATION"
    PLACE = "PLACE"
    PHOTO = "PHOTO"
    ALBUM = "ALBUM"


class DDBClient:
    PARTITION_KEY = "PK"
    SORT_KEY = "SK"
    ENTITY = "Entity"

    def __init__(self, session: boto3.resource, table_name: str):
        self._session = session
        self.table_name = table_name
        self.table = session.resource("dynamodb").Table(
            "michaeljscullydotcom-storageStack-prod-personalSiteTable68E02C46-17FYKB4CR7NKK"
        )

    def _query_table(self, filtering_exp):
        # assert partition_key != None
        # filtering_exp = Key(self.PARTITION_KEY).eq(partition_key)
        # if sort_key:
        #     filtering_exp = filtering_exp & Key(self.SORT_KEY).eq(sort_key)
        resp = self.table.query(KeyConditionExpression=filtering_exp)
        return [item["Entity"] for item in resp["Items"]]

    def _put_item(self, data):
        resp = self.table.put_item(Item=data)

        assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200
        return True

    def _delete_item(self, pk, sk):
        key = {self.PARTITION_KEY: pk}
        if sk:
            key[self.SORT_KEY] = sk

        resp = self.table.delete_item(Key=key)

        assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200

    def get_keys(self):
        id_key = self.sort_key if self.sort_key else self.partition_key
        scan_kwargs = {"ProjectionExpression": f"{id_key}"}

        keys = []

        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key
            response = self.table.scan(**scan_kwargs)
            keys += [k[id_key] for k in response["Items"]]
            start_key = response.get("LastEvaluatedKey", None)
            done = start_key is None

        return keys

    def get_equals(self, partition_key, sort_key=None):
        filtering_exp = Key(self.PARTITION_KEY).eq(partition_key)
        if sort_key:
            filtering_exp = filtering_exp & Key(self.SORT_KEY).eq(sort_key)
        return self._query_table(filtering_exp)

    def get_begins_with(self, partition_key, sort_key):
        filtering_exp = Key(self.PARTITION_KEY).eq(partition_key) & Key(
            self.SORT_KEY
        ).begins_with(sort_key)
        return self._query_table(filtering_exp)

    def put(self, pk, sk, entity):
        data = {self.PARTITION_KEY: pk, self.SORT_KEY: sk, self.ENTITY: entity}
        self._put_item(data)

    def delete(self, pk, sk):
        self._delete_item(pk, sk)
