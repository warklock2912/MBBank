from PIL import Image
import pytesseract
import re
import datetime
import base64
import hashlib
import typing
import io
import platform
import aiohttp

headers_default = {
    'Cache-Control': 'no-cache',
    'Accept': 'application/json, text/plain, */*',
    'Authorization': 'Basic RU1CUkVUQUlMV0VCOlNEMjM0ZGZnMzQlI0BGR0AzNHNmc2RmNDU4NDNm',
    'User-Agent': f'Mozilla/5.0 (X11; {platform.system()} {platform.processor()})',
    "Origin": "https://online.mbbank.com.vn",
    "Referer": "https://online.mbbank.com.vn/"
}


def get_now_time():
    now = datetime.datetime.now()
    microsecond = int(now.strftime("%f")[:2])
    return now.strftime(f"%Y%m%d%H%M{microsecond}")


class MBBankAsync:
    deviceIdCommon = f'yeumtmdx-mbib-0000-0000-{get_now_time()}'

    def __init__(self, *, username, password, tesseract_path=None):
        self.__userid = username
        self.__password = password
        if tesseract_path is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self.sessionId = None
        self._userinfo = None
        self._temp = {}

    async def _req(self, url, *, json={}, headers={}):
        while True:
            if self.sessionId is None:
                await self.authenticate()
            rid = f"{self.__userid}-{get_now_time()}"
            json_data = {
                'sessionId': self.sessionId if self.sessionId is not None else "",
                'refNo': rid,
                'deviceIdCommon': self.deviceIdCommon,
            }
            json_data.update(json)
            headers.update(headers_default)
            headers["X-Request-Id"] = rid
            async with aiohttp.ClientSession() as s:
                async with s.post(url, headers=headers, json=json_data) as r:
                    data_out = await r.json()
            if data_out["result"] is None:
                await self.getBalance()
            elif data_out["result"]["ok"]:
                data_out.pop("result", None)
                break
            elif data_out["result"]["responseCode"] == "GW200":
                await self.authenticate()
            else:
                err_out = data_out["result"]
                raise Exception(f"{err_out['responseCode']} | {err_out['message']}")
        return data_out

    async def authenticate(self):
        while True:
            self._userinfo = None
            self.sessionId = None
            self._temp = {}
            rid = f"{self.__userid}-{get_now_time()}"
            json_data = {
                'sessionId': "",
                'refNo': rid,
                'deviceIdCommon': self.deviceIdCommon,
            }
            headers = headers_default.copy()
            headers["X-Request-Id"] = rid
            async with aiohttp.ClientSession() as s:
                async with s.post("https://online.mbbank.com.vn/retail-web-internetbankingms/getCaptchaImage",
                                  headers=headers, json=json_data) as r:
                    data_out = await r.json()
            img_byte = io.BytesIO(base64.b64decode(data_out["imageString"]))
            img = Image.open(img_byte)
            img = img.convert('RGBA')
            pix = img.load()
            for y in range(img.size[1]):
                for x in range(img.size[0]):
                    if pix[x, y][0] < 102 or pix[x, y][1] < 102 or pix[x, y][2] < 102:
                        pix[x, y] = (0, 0, 0, 255)
                    else:
                        pix[x, y] = (255, 255, 255, 255)
            text = pytesseract.image_to_string(img)
            text = re.sub(r"\s+", "", text, flags=re.MULTILINE)
            payload = {
                "userId": self.__userid,
                "password": hashlib.md5(self.__password.encode()).hexdigest(),
                "captcha": text,
                'sessionId': "",
                'refNo': f'{self.__userid}-{get_now_time()}',
                'deviceIdCommon': self.deviceIdCommon,
            }
            async with aiohttp.ClientSession() as s:
                async with s.post("https://online.mbbank.com.vn/retail_web/internetbanking/doLogin",
                                  headers=headers_default, json=payload) as r:
                    data_out = await r.json()
            if data_out["result"]["ok"]:
                self.sessionId = data_out["sessionId"]
                self._userinfo = data_out
                return
            elif data_out["result"]["responseCode"] == "GW283":
                pass
            else:
                err_out = data_out["result"]
                raise Exception(f"{err_out['responseCode']} | {err_out['message']}")

    async def getTransactionAccountHistory(self, *, accountNo: str = None, from_date: datetime.datetime,
                                           to_date: datetime.datetime):
        json_data = {
            'accountNo': self.__userid if accountNo is None else accountNo,
            'fromDate': from_date.strftime("%d/%m/%Y"),
            'toDate': to_date.strftime("%d/%m/%Y"),  # max 3 months
        }
        data_out = await self._req(
            "https://online.mbbank.com.vn/api/retail-transactionms/transactionms/get-account-transaction-history",
            json=json_data)
        return data_out

    async def getBalance(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail-web-accountms/getBalance")
        return data_out

    async def getBalanceLoyalty(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/loyalty/getBalanceLoyalty")
        return data_out

    async def getInterestRate(self, currency: str = "VND"):
        json_data = {
            "productCode": "TIENGUI.KHN.EMB",
            "currency": currency,
        }
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/saving/getInterestRate", json=json_data)
        return data_out

    async def getFavorBeneficiaryList(self, *, transactionType: typing.Literal["TRANSFER", "PAYMENT"],
                                      searchType: typing.Literal["MOST", "LATEST"]):
        json_data = {
            "transactionType": transactionType,
            "searchType": searchType
        }
        data_out = await self._req(
            "https://online.mbbank.com.vn/api/retail_web/internetbanking/getFavorBeneficiaryList", json=json_data)
        return data_out

    async def getCardList(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/card/getList")
        return data_out

    async def getSavingList(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/saving/getList")
        return data_out

    async def getLoanList(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/loan/getList")
        return data_out

    async def userinfo(self):
        if self._userinfo is None:
            await self.authenticate()
        else:
            await self.getBalance()
        return self._userinfo

    async def getBankList(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/common/getBankList")
        return data_out

    async def inquiryAccountName(self, *, typeTransfer: str = None, debitAccount: str, bankCode: str = None,
                                 creditAccount: str, creditAccountType: typing.Literal["ACCOUNT", "CARD"]):
        creditCardNo = None
        if (bankCode is None or typeTransfer is None) and creditAccountType != "CARD":
            raise TypeError("creditAccount must be \"CARD\" so bankCode or typeTransfer can be None")
        elif creditAccountType == "CARD":
            out = await self.getBankList()
            for i in out['listBank']:
                bankCode = None
                typeTransfer = None
                if creditAccount.startswith(i["smlCode"]):
                    bankCode = i["smlCode"]
                    typeTransfer = i["typeTransfer"]
                    datacard = await self.cardGenerateID(creditAccount)
                    creditCardNo = datacard["cardNumber"]
                    creditAccount = datacard["cardID"]
                    break
            if bankCode is None or typeTransfer is None:
                raise Exception(f"Invaild card")
            elif not creditAccount:
                raise Exception(f"Card not exist")
        json_data = {
            "creditAccount": creditAccount,
            "creditAccountType": creditAccountType,
            "bankCode": bankCode,
            "debitAccount": debitAccount,
            "type": typeTransfer,
            "remark": "",
        }
        if creditCardNo is not None:
            json_data.setdefault("creditCardNo", creditCardNo)
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/transfer/inquiryAccountName",
                                   json=json_data)
        return data_out

    async def getServiceToken(self):
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/common/getServiceToken")
        return data_out

    async def cardGenerateID(self, cardNumber: str):
        headers = headers_default.copy()
        json_data = {
            "requestID": f"{self.__userid}-{get_now_time()}",
            "cardNumber": cardNumber
        }
        tok = await self.getServiceToken()
        headers["Authorization"] = tok["type"].capitalize() + " " + tok["token"]
        async with aiohttp.ClientSession() as s:
            async with s.post("https://mbcard.mbbank.com.vn:8446/mbcardgw/internet/cardinfo/v1_0/generateid",
                              headers=headers, json=json_data) as r:
                return await r.json()

    async def getAccountByPhone(self, phone: str):
        json_data = {
            "phone": phone
        }
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/common/getAccountByPhone",
                                   json=json_data)
        return data_out

    async def getCardTransactionHistory(self, cardNo: str, from_date: datetime.datetime, to_date: datetime.datetime):
        json_data = {
            "accountNo": cardNo,
            "fromDate": from_date.strftime("%d/%m/%Y"),
            "toDate": to_date.strftime("%d/%m/%Y"),  # max 3 months
            "historyNumber": "",
            "historyType": "DATE_RANGE",
            "type": "CARD",
        }
        data_out = await self._req("https://online.mbbank.com.vn/api/retail_web/common/getTransactionHistory",
                                   json=json_data)
        return data_out
