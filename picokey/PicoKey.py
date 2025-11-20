"""
/*
 * This file is part of the pypicokey distribution (https://github.com/polhenarejos/pypicokey).
 * Copyright (c) 2025 Pol Henarejos.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
"""

import sys
from .APDU import APDUResponse
from .SecureChannel import SecureChannel
from .RescuePicoKey import RescuePicoKey
from .PhyData import PhyData
from .core import NamedIntEnum

class Platform(NamedIntEnum):
    RP2040 = 0
    RP2350 = 1
    ESP32  = 2
    EMULATION = 3

class Product(NamedIntEnum):
    UNKNOWN = 0
    HSM     = 1
    FIDO    = 2
    OPENPGP = 3

class PicoKey:
    def __init__(self, slot=-1, force_rescue=False):
        self.__sc = None
        if (force_rescue):
            try:
                self.__card = RescuePicoKey()
            except Exception:
                raise Exception('time-out: no card inserted')
        else:
            from smartcard.CardType import AnyCardType
            from smartcard.CardRequest import CardRequest
            cardtype = AnyCardType()
            try:
                # request card insertion
                readers = None
                if (slot >= 0):
                    readers = CardRequest().getReaders()
                    if (slot >= len(readers)):
                        raise Exception('slot out of range')
                    readers = [readers[slot]]
                cardrequest = CardRequest(timeout=1, cardType=cardtype, readers=readers)
                self.__card = cardrequest.waitforcard().connection

                # connect to the card and perform a few transmits
                self.__card.connect()

            except Exception:
                try:
                    self.__card = RescuePicoKey()
                except Exception:
                    raise Exception('time-out: no card inserted')
        resp, sw1, sw2 = self.select_applet(rescue=True)
        try:
            resp, sw1, sw2 = self.select_applet(rescue=True)
            if (sw1 == 0x90 and sw2 == 0x00):
                self.platform = Platform(resp[0])
                self.product = Product(resp[1])
                self.version = (resp[2], resp[3])
        except APDUResponse:
            self.platform = Platform(Platform.RP2040)
            self.product = Product(Product.UNKNOWN)
            self.version = (0, 0)

    def transmit(self, apdu):
        response, sw1, sw2 = self.__card.transmit(apdu)
        return response, sw1, sw2

    def send(self, command, cla=0x00, p1=0x00, p2=0x00, ne=None, data=None, codes=[]):
        lc = []
        dataf = []
        if (data):
            lc = [0x00] + list(len(data).to_bytes(2, 'big'))
            dataf = list(data)
        else:
            lc = [0x00*3]
        if (ne is None):
            le = [0x00, 0x00]
        else:
            le = list(ne.to_bytes(2, 'big'))
        if (isinstance(command, list) and len(command) > 1):
            apdu = command
        else:
            apdu = [cla, command]

        apdu = apdu + [p1, p2] + lc + dataf + le
        self.__apdu = apdu
        if (self.__sc):
            apdu = self.__sc.wrap_apdu(apdu)

        try:
            response, sw1, sw2 = self.__card.transmit(apdu)
        except Exception:
            self.__card.reconnect()
            response, sw1, sw2 = self.__card.transmit(apdu)

        code = (sw1<<8|sw2)
        if (sw1 != 0x90):
            if (sw1 == 0x63 and sw2 & 0xF0 == 0xC0):
                pass
            # elif (code == 0x6A82):
            #     self.select_applet()
            #     if (sw1 == 0x90):
            #         response, sw1, sw2 = self.__card.transmit(apdu)
            #         if (sw1 == 0x90):
            #             return response
            elif (sw1 == 0x61):
                response = []
                while (sw1 == 0x61):
                    apdu = [0x00, 0xC0, 0x00, 0x00, sw2]
                    resp, sw1, sw2 = self.__card.transmit(apdu)
                    response += resp
                code = (sw1<<8|sw2)
            if (code not in codes and code != 0x9000):
                raise APDUResponse(sw1, sw2)
        if (self.__sc):
            response, code = self.__sc.unwrap_rapdu(response)
            if (code not in codes and code != 0x9000):
                raise APDUResponse(code >> 8, code & 0xff)
        return bytes(response), code

    def resend(self):
        apdu = self.__apdu
        if (self.__sc):
            apdu = self.__sc.wrap_apdu(apdu)

        try:
            response, sw1, sw2 = self.__card.transmit(apdu)
        except Exception:
            self.__card.reconnect()
            response, sw1, sw2 = self.__card.transmit(apdu)

        return bytes(response), sw1, sw2

    def open_secure_channel(self, shared, nonce, token, pbkeyBytes):
        sc = SecureChannel(shared=shared, nonce=nonce)
        res = sc.verify_token(token, pbkeyBytes)
        if (not res):
            raise Exception('Secure Channel token verification failed')
        self.__sc = sc

    def select_applet(self, rescue=False):
        if (rescue):
            return self.transmit([0x00, 0xA4, 0x04, 0x04, 0x08, 0xA0, 0x58, 0x3F, 0xC1, 0x9B, 0x7E, 0x4F, 0x21, 0x00])
        return self.transmit([0x00, 0xA4, 0x04, 0x00, 0x0B, 0xE8, 0x2B, 0x06, 0x01, 0x04, 0x01, 0x81, 0xC3, 0x1F, 0x02, 0x01, 0x00])

    def phy(self, data=None):
        if (data is None):
            try:
                resp, sw = self.send(0x1E, cla=0x80, p1=0x00, ne=256)
                return PhyData.parse(resp)
            except APDUResponse:
                pass
            return None
        else:
            self.send(0x1C, cla=0x80, p1=0x01, data=data)

    def flash_info(self):
        try:
            resp, sw = self.send(0x1E, cla=0x80, p1=0x02)
            free = int.from_bytes(resp[0:4], 'big')
            used = int.from_bytes(resp[4:8], 'big')
            total = int.from_bytes(resp[8:12], 'big')
            nfiles = int.from_bytes(resp[12:16], 'big')
            size = int.from_bytes(resp[16:20], 'big')
        except Exception:
            free = used = total = nfiles = size = 0
        return {
            'free': free,
            'used': used,
            'total': total,
            'nfiles': nfiles,
            'size': size
        }

    def secure_info(self):
        resp, sw = self.send(0x1E, cla=0x80, p1=0x03)
        return {
            'enabled': resp[0] != 0,
            'locked': resp[1] != 0,
            'boot_key': resp[2]
        }

    def secure_boot(self, bootkey_index=0, lock=False):
        data = bytes([bootkey_index & 0xFF, 1 if lock else 0])
        self.send(0x1C, cla=0x80, p1=0x02, data=data)
