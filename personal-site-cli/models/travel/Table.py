import pprint
from boto3.dynamodb.conditions import Key

class Table(object):
    def __init__(self, table, type_, partition_key, sort_key=None):
        self.table = table
        self.partition_key = partition_key
        self.sort_key = sort_key
        self.type = type_

    def _scan_table(self):
        resp = self.table.scan()
        return [self.type(**item) for item in resp['Items']]


    def _query_table(self, partition_key_value=None, sort_key_value=None):
        assert partition_key_value != None
        filtering_exp = Key(self.partition_key).eq(partition_key_value)
        if sort_key_value:
            assert self.sort_key
            filtering_exp = filtering_exp & Key(self.sort_key).eq(sort_key_value)
        resp = self.table.query(KeyConditionExpression=filtering_exp)
        return [self.type(**item) for item in resp['Items']]

    def _put_item(self, data):
        resp = self.table.put_item(
            Item=data
        )

        assert resp['ResponseMetadata']['HTTPStatusCode'] == 200
        return True

    # def _append_to_list(self, data):
    #     key = {
    #         'hash_key': data.get(self.partition_key),
    #     }
    #     if self.sort_key:
    #         key['range_key'] = data.get(self.sort_key)

    #     resp = self.table.update_item(
    #         Key=key,       
    #         UpdateExpression="SET some_attr = list_append(photos, :i)",
    #         ExpressionAttributeValues={
    #             ':i': data["list"],
    #         },
    #     )
    #     return resp

    def _delete_item(self, data):
        key = {
            self.partition_key: data[self.partition_key]
        }
        if self.sort_key:
            key[self.sort_key] = data[self.sort_key]

        resp = self.table.delete_item(
            Key=key
        )

        assert resp['ResponseMetadata']['HTTPStatusCode'] == 200

    def get_keys(self):
        id_key = self.sort_key if self.sort_key else self.partition_key
        scan_kwargs = {
            'ProjectionExpression': f"{id_key}"
        }

        keys = []

        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs['ExclusiveStartKey'] = start_key
            response = self.table.scan(**scan_kwargs)
            keys += [k[id_key] for k in response['Items']]
            start_key = response.get('LastEvaluatedKey', None)
            done = start_key is None

        return keys

    def get(self, partition_key_value=None, sort_key_value=None, return_type=None):
        if sort_key_value:
            assert partition_key_value
            # return self._get_item(partition_key_value=partition_key_value, sort_key_value=sort_key_value)
            return self._query_table(partition_key_value=partition_key_value, sort_key_value=sort_key_value)
        elif partition_key_value:
            return self._query_table(partition_key_value=partition_key_value)
        else:
            return self._scan_table()

    def insert(self, obj):
        if hasattr(obj, "serialize"):
            self._put_item(obj.serialize())
        else:
            self._put_item(obj)

    def update(self, obj):
        if hasattr(obj, "serialize"):
            self._put_item(obj.serialize())
    
    def delete(self, obj):
        if hasattr(obj, "serialize"):
            self._delete_item(obj.serialize())

# if __name__ == "__main__":
#     from DynamoDB import create_dynamo_resource, create_dynamo_table_client

#     from constants import TABLE_KEYS, TABLE_NAMES
#     db = create_dynamo_resource()
#     photos_table = Table(
#         create_dynamo_table_client(db, TABLE_NAMES.PHOTOS), 
#         partition_key=TABLE_KEYS.PHOTOS.PARTITION_KEY, 
#         sort_key=TABLE_KEYS.PHOTOS.SORT_KEY
#     )

#     resp = photos_table.table.put_item(                        
#         Item={
#             "destination_id": "boof",
#             "place_id": "chrok",
#             "photos": ({}, {})
#             }
#     )