#!/usr/bin/python3
import argparse
import boto3
import time


def invoke_sfn(s3_bucket, s3_key):
    lambda_client = boto3.client('lambda', region_name=args.region)
    lambda_client.invoke(
        FunctionName='preprocessing-{}-pipeline-trigger'.format(args.environment),
        Payload='{"Records":[{"s3":{"bucket":{"name":"' + s3_bucket + '"},"object":{"key":"' + s3_key + '"}}}]}',
    )

ALL_FILES = [
    '04fb647b-e563-480c-a70c-a80c0436602f',
    '0505130a-6a97-4e09-a5b3-eec56d7d400c',
    '05a6d065-c7b9-494d-877e-93dbf19169bb',
    '0ad5e871-2ad6-4d5f-9ecf-e8a3fe81f25f',
    '0c168b25-9db7-49b4-8b31-50cbcadf9c73',
    '0cf5390f-84ac-4052-80f4-cdd9ca5abb9c',
    '0d21309a-63ad-4c28-865e-b76ff1b3771a',
    '0d9157c9-dbf2-45dc-aa83-e3049302794b',
    '0de22f02-0ef1-4b99-88cf-c21c6e13cb9c',
    '0f35c03e-d623-4b31-aedf-c467a81cbfbe',
    '164588ca-bfe8-4b78-b824-362602a5cecb',
    '1cd80644-234e-437e-ba87-10838ce2e651',
    '1cf4acd5-a2bb-4e4c-9565-7785204bfd29',
    '1e15208a-252d-42ac-b0c9-fef4249e204d',
    '20077fea-1556-496e-959b-c9aaaf6e6bd0',
    '2169071a-99f7-43a9-b2aa-65faba16b727',
    '218cbfcd-0505-48d3-990c-743dec10f219',
    '26fd3629-5877-4f43-bf15-2fe7ba42623c',
    '2746c4b7-f56f-4635-be37-2d46b264ed51',
    '2854341b-becd-48a3-9f21-db887d093443',
    '28cda022-a4c3-4457-84ed-370265f7e43d',
    '2b2c635f-ace8-429e-bd85-8f539bfb7092',
    '2f850365-c525-4960-b0d8-e38824bc3cae',
    '31a145ee-ed8e-47f3-89e3-b175b025a0bf',
    '31dd9c2b-498a-4575-9dab-83f8a19e96e9',
    '37122c15-46b3-4791-92b2-e4f5582cba5d',
    '38040983-5de3-4f8a-9f12-c2716a61f9fb',
    '3956adf3-0446-4ad7-97b5-6442d3ceef90',
    '395e2eb4-df14-4f44-9a40-9f5f6b9ea65b',
    '3a181d0d-64f9-4287-9a64-28c054aeb087',
    '3cc56e2b-9b17-42cc-9028-6ca44674bd0c',
    '3d911945-0eaf-441e-a309-f052cb27236d',
    '3ffac6af-b7a3-4354-b6c0-c33accc3855a',
    '41a5aa49-0390-467f-9da7-cc900d881767',
    '47819a0f-5c14-4ae2-a96c-fa7224308c76',
    '4b2073de-ee4d-4c89-9635-e337b3870747',
    '4eef286f-6a4b-4728-9c09-958c7677123b',
    '4fee6545-4626-4032-9674-9b09a45cff1e',
    '53cc11c7-5a02-406c-81c4-38547e7282fb',
    '53fcbec1-5616-43c5-b83d-17410fdcff8b',
    '5496db12-e445-40f6-a71e-2ee3c44c3b53',
    '54aa6272-432e-4806-9249-f61d3397ca35',
    '55d29a6c-207f-4dc5-81ab-eb4345cd2298',
    '5631bc29-a368-4fc0-86cf-c6b7f26cf7d3',
    '589595f7-35e2-4bce-9cea-28c64590c323',
    '5d899bd7-31d2-444f-9262-0b8d9b8c833f',
    '5ec33235-0372-4e9b-b47f-807f86fc90e3',
    '5fdafcef-fc72-4c50-85b4-5196faa2b8f6',
    '605a9a17-24bf-4fdc-b539-02adbb28a628',
    '6194220a-f8b9-4946-97a3-0f91138f1188',
    '62f3023c-4786-482d-8b7d-1e192f17a301',
    '636524ff-c338-440f-a570-38fddcab93cd',
    '63a8c2dd-208a-4d94-a7b0-7eb021907abb',
    '63cc2fd5-0615-44a9-b479-1dc64179b74b',
    '64680b3c-d425-4e0a-8547-debaa8d22519',
    '688a0cbc-a2cf-44b9-af7d-b7b21d935a4f',
    '6b24e229-de72-48b3-9704-5e2065d7aadf',
    '6cf4391a-0bd9-4213-951a-1c5dce230a1c',
    '70f5b165-66ef-402f-bb55-af44dbc97a05',
    '7390c447-5735-4486-99b2-6da54d54114f',
    '74923a3c-eff0-4ad9-b3b1-ad80d23c492a',
    '75b9e6cd-cccc-4e67-a169-97035675f804',
    '7ba08a04-a5b4-417a-b107-2c0917d986f1',
    '83f9ddf2-2cf6-4d5f-99c7-54e847ea6392',
    '84067487-2090-489f-a909-ddc68eeb5308',
    '84a36097-d500-416b-b358-bbfdfcffd935',
    '8518ab90-32ab-4ff3-a090-f92f2af11d23',
    '898ab3f7-a0a2-402a-8b0d-a882b8f3f466',
    '8af4ab42-d9d9-40b7-bf53-def22cf45b6a',
    '90a83783-d284-428a-b65d-1f3550147560',
    '923b605f-1863-4271-a6f7-129c0da683f7',
    '96810b0f-4950-40ac-9d82-b792beb725c2',
    '9829f2be-49b8-47f8-92fb-b27c9cf036a6',
    '9c70cc19-d986-4123-a501-125a6901aeba',
    '9cd2aa54-0f4a-45be-9751-e792255b418d',
    '9db1b27f-9743-4e3f-9362-ddc2a95f0832',
    '9ed7624d-b0b0-4797-a9b3-fe227bb7c098',
    '9f21408b-44b9-4637-8abe-caafc61e99bb',
    '9febb038-7971-4228-af8a-496c3d00cb77',
    'a234ee01-710d-4404-aae9-fbe65b34f8c5',
    'a92822ee-d719-400a-a4a8-69bfcec97a9c',
    'aa5fc9ef-0271-4af4-9baf-9d98debf26a7',
    'aad78a1c-fcc8-48fe-bfe4-93ebf5bed7ad',
    'b97c97f9-a56d-4e18-81a5-777452bd278d',
    'ba0ce3a8-a196-4f16-bb72-e3b482a67867',
    'ba3d6c85-89b9-4cad-89bc-857b329359ea',
    'bc88ddff-8ac0-446a-8b7b-8077812e338c',
    'bd5fb315-94ce-4549-9d93-016f6eaa481c',
    'c1ecad3c-857a-408e-b07a-5f4e670d1f15',
    'c2e04d26-7e15-4f64-97b5-8878e4183655',
    'c57b79e2-0eef-4f6f-b783-584ceaa9769d',
    'c9cc81f5-207c-49b5-b732-7d9aff1fa573',
    'cba3e1e7-876e-4984-99d7-26c93048e423',
    'd07e22fa-6bd3-4897-97b2-5f9554807f62',
    'd2a31c2a-9451-45d6-a955-47dafa8f8d0b',
    'd4bcee28-2757-45c8-8a6c-b35843f7bd3b',
    'd4c53d3f-70de-4289-ab46-aad08b6f9fc2',
    'da2f3d5a-06d7-47fc-a5f9-864ad6e29b01',
    'dd86cf5d-9fba-49f2-a5e6-495187edfb8a',
    'ddad7792-2cba-4d50-b4c6-64363f709370',
    'e1b65120-c948-427f-b8ff-b5c517b41edb',
    'e3eef7a2-4699-459c-9a10-c3712b5062b0',
    'e4584067-f173-4ddc-8724-29bf2d08a32f',
    'e6bdac59-7c0e-49a2-9088-9b6bc18abea3',
    'e83bdc81-7491-42bb-889a-0e21501853e8',
    'e859a8a3-6c33-49c0-b2cf-2f1288a7dd3c',
    'e867d15a-8e4a-431b-9525-14e1143ea7e2',
    'f0cfb229-fec8-4424-9de8-ab706f12f51e',
    'f15fd539-5c0f-4b3b-be91-e0080aee787a',
    'f1811ed7-802a-469b-87a3-9abb315288b4',
    'f6d80852-d9ac-47d2-9007-a1c2b201f749',
    'f78e9189-6b47-4fe0-9682-b3d8ff660691',
    'fc55f19c-c0e2-4bb3-81af-2de544d399e9',
    'ff95637a-dedb-4279-87a2-4948cc4c6e89',

]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Invoke one or more test files')
    parser.add_argument('start',
                        type=int,
                        help='The start point')
    parser.add_argument('number',
                        type=int,
                        help='The number of files to run')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        default='us-west-2')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--bucket', '-b',
                        type=str,
                        help='S3 bucket',
                        default='biometrix-testdatav2')
    parser.add_argument('--delay', '-d',
                        type=int,
                        help='Delay between invocations (secs)',
                        default=0)

    args = parser.parse_args()

    files = ALL_FILES[args.start:args.start+args.number]

    count = 1
    for key in files:
        print('Invoking  {count}/{total} ({key})'.format(count=count, total=len(files), key=key))
        invoke_sfn(args.bucket, key)
        time.sleep(args.delay)
        count += 1
