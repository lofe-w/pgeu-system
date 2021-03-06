import json
from uuid import uuid4
from time import time
from datetime import timedelta
from decimal import Decimal
from Cryptodome.Signature import PKCS1_v1_5
from Cryptodome.Hash import SHA
from Cryptodome.PublicKey import RSA
import base64
import requests


class TrustlyException(Exception):
    pass


class TrustlyWrapper(object):
    def __init__(self, apibase, username, password, privatekey, publickey, notificationurl, currency='EUR', hold_notifications=False):
        self.apibase = apibase
        self.username = username
        self.password = password
        self.signer = PKCS1_v1_5.new(RSA.importKey(privatekey))
        self.verifier = PKCS1_v1_5.new(RSA.importKey(publickey))
        self.notificationurl = notificationurl
        self.currency = currency
        self.hold_notifications = hold_notifications

    def new_uuid(self):
        return str(uuid4())

    def deposit(self, enduserid, invoiceid, amount, shopperstatement, successurl, failurl, firstname=None, lastname=None, email=None, ip=None):
        d = {
            'NotificationURL': self.notificationurl,
            'EndUserID': enduserid,
            'MessageID': "{0}-{1}".format(invoiceid, time()),
            'Attributes': {
                'Currency': self.currency,
                'Firstname': firstname,
                'Lastname': lastname,
                'Email': email,
                'IP': ip,
                'SuccessURL': successurl,
                'FailURL': failurl,
                'ShopperStatement': shopperstatement,
                'Amount': '{0:.2f}'.format(amount),
            },
        }
        if self.hold_notifications:
            d['Attributes']['HoldNotifications'] = '1'
        return self.apicall('Deposit', d)

    def refund(self, orderid, amount):
        r = self.apicall('Refund', {
            'OrderID': str(orderid),
            'Amount': '{0:.2f}'.format(amount),
            'Currency': self.currency,
        })
        if r['data']['result'] == '1':
            # Yay! Successful. But what about the orderid?
            if r['data']['orderid'] != str(orderid):
                raise TrustlyException('Refunded orderid {0} does not match requested orderid {1}'.format(
                    r['data']['orderid'], orderid))
            return True
        else:
            raise TrustlyException('Failed to refund orderid {0}'.format(orderid))

    def get_balance(self):
        r = self.apicall('Balance', {})
        balance = None
        for b in r['data']:
            # We can get multiple balances. If we see a non-zero balance for a non-standard
            # currency, bail.
            if b['currency'] == self.currency:
                balance = Decimal(b['balance'])
            else:
                # Different currency, so ensure it's zero
                if Decimal(b['balance']) != 0:
                    raise TrustlyException('Found non-zero balance {0} for non-standard currency {1}'.format(b['balance'], b['currency']))
        if balance is None:
            raise TrustlyException('Found no balance for {0}'.format(self.currency))
        return balance

    def getwithdrawal(self, orderid):
        r = self.apicall('GetWithdrawals', {'OrderID': orderid})
        w = r['data']
        if len(w) == 0:
            # No withdrawal found, so nothing to match yet
            return None
        elif len(w) != 1:
            raise TrustlyException('Received more than one withdrawal for order {0}'.format(orderid))
        return w[0]

    def getledgerforday(self, day):
        return self.getledgerforrange(day, day + timedelta(hours=24))

    def getledgerforrange(self, fromday, today):
        r = self.apicall('AccountLedger', {
            'FromDate': fromday.strftime('%Y-%m-%d'),
            'ToDate': today.strftime('%Y-%m-%d'),
            'Currency': self.currency,
        })
        return r['data']

    def apicall(self, method, data):
        params = {
            'UUID': self.new_uuid(),
            'Data': data,
        }
        params['Data']['Username'] = self.username
        params['Data']['Password'] = self.password
        tosign = method + params['UUID'] + self._serializestruct(params['Data'])
        sha1hash = SHA.new(tosign.encode('utf-8'))
        signature = self.signer.sign(sha1hash)
        params['Signature'] = base64.b64encode(signature).decode('utf8')
        p = {
            'method': method,
            'params': params,
            'version': '1.1',
        }

        resp = requests.post(self.apibase, json=p)
        if resp.status_code != 200:
            raise TrustlyException("bad http response code {0}".format(resp.status_code))
        r = resp.json()
        if 'error' in r:
            # XXX log and raise generic exception!
            raise TrustlyException(r['error']['message'])
        if r['result']['method'] != method:
            raise TrustlyException("bad method in response")

        # XXX: verify signature? But we made a https call...
        return r['result']

    def parse_notification(self, notstr):
        struct = json.loads(notstr)
        tosign = struct['method'] + struct['params']['uuid'] + self._serializestruct(struct['params']['data'])
        sha1hash = SHA.new(tosign.encode('utf-8'))

        if self.verifier.verify(sha1hash, base64.b64decode(struct['params']['signature'])):
            return (struct['params']['uuid'], struct['method'], struct['params']['data'])
        else:
            # Indicate that signature failed
            return (struct['params']['uuid'], struct['method'], None)

    def create_notification_response(self, uuid, method, status):
        struct = {
            'result': {
                'uuid': uuid,
                'method': method,
                'data': {
                    'status': status,
                }
            },
            'version': '1.1',
        }
        tosign = method + uuid + self._serializestruct(struct['result']['data'])
        sha1hash = SHA.new(tosign.encode('utf-8'))
        signature = self.signer.sign(sha1hash)
        struct['result']['signature'] = base64.b64encode(signature).decode('utf8')
        return json.dumps(struct)

    def _serializestruct(self, struct):
        if (type(struct) == dict):
            serialized = ''
            for k in sorted(struct.keys()):
                if struct[k]:
                    serialized += k
                    serialized += self._serializestruct(struct[k])
                else:
                    serialized += k
            return serialized
        # XXX: Handle regular arrays?
        else:
            return str(struct)
