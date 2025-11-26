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

from typing import Optional
import threading
from .APDU import APDUResponse
from .SecureChannel import SecureChannel
from .RescuePicoKey import RescuePicoKey
from .RescueMonitor import RescueMonitor, RescueMonitorObserver
from .PhyData import PhyData
from .core import NamedIntEnum
import usb.core

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

class ConnectionType(NamedIntEnum):
    UNKNOWN = 0
    SMARTCARD = 1
    RESCUE = 2

class ConnectTimeout(Exception):
    pass

def connect_with_timeout(connection, timeout=2.0):
    result = {}

    def worker():
        try:
            connection.connect()
            result["ok"] = True
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise ConnectTimeout("connection.connect() timed out")

    if "error" in result:
        raise result["error"]

    return True

class PicoKey:

    def __init__(self, slot=-1, force_rescue=False):
        self.__sc = None
        self.__card = None

        if (not force_rescue):
            from smartcard.System import readers
            import smartcard.Exceptions
            from smartcard.CardMonitoring import CardMonitor, CardObserver

            class PicoCardObserver(CardObserver):
                def __init__(self, device):
                    self.__device = device

                def update(self, observable, actions):
                    (added, removed) = actions
                    if added:
                        pass
                    if removed:
                        self.__device.close()

            def reader_has_card(reader):
                try:
                    connection = reader.createConnection()
                    connect_with_timeout(connection, timeout=1.0)
                    return connection
                except smartcard.Exceptions.NoCardException:
                    return None
                return None

            try:
                rdrs = readers()
            except Exception as e:
                rdrs = []
            if len(rdrs) > 0:
                if (slot >= 0 and slot >= len(rdrs)):
                    raise Exception('Slot number out of range')

                if (slot >= 0 and slot < len(rdrs)):
                    reader = rdrs[slot]
                    connection = reader_has_card(reader)
                    if (connection is None):
                        raise Exception(f'No card in reader slot {slot}')
                    self.__card = connection
                else:
                    for i, reader in enumerate(rdrs):
                        reader = rdrs[i]
                        connection = reader_has_card(reader)
                        if (connection is None):
                            continue
                        self.__card = connection
                        self.__connection_type = ConnectionType.SMARTCARD

                        self.__monitor = CardMonitor()
                        self.__observer = PicoCardObserver(self)
                        self.__monitor.addObserver(self.__observer)
                        break

        if (self.__card is None):
            class PicoRescueObserver(RescueMonitorObserver):
                def __init__(self, device):
                    self.__device = device

                def update(self, actions: tuple[Optional[usb.core.Device], Optional[usb.core.Device]]):
                    (connected, disconnected) = actions
                    if connected:
                        pass
                    if disconnected:
                        self.__device.close()
            try:
                self.__card = RescuePicoKey()
                self.__connection_type = ConnectionType.RESCUE
                self.__observer = PicoRescueObserver(self)
                self.__monitor = RescueMonitor(device=self.__card, cls_callback=self.__observer)
            except Exception:
                raise Exception('time-out: no card inserted')
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

    @property
    def device(self):
        return self.__card

    def has_device(self):
        return self.__card is not None

    @property
    def connection_type(self):
        return self.__connection_type

    def close(self):
        if (not self.__card):
            return
        if isinstance(self.__card, RescuePicoKey):
            self.__monitor.stop()
            self.__monitor = None
            self.__observer = None
            self.__card.close()
        else:
            self.__card.disconnect()
            self.__card.release()
        self.__card = None

    def transmit(self, apdu: list[int]):
        if (not self.__card):
            raise Exception('No device connected')
        response, sw1, sw2 = self.__card.transmit(apdu)
        return response, sw1, sw2

    def send(self, command: int, cla: int = 0x00, p1: int =0x00, p2: int=0x00, ne : Optional[int] = None, data : Optional[list[int]] = None, codes : list[int] = []):
        if (not self.__card):
            raise Exception('No device connected')
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
            try:
                response, sw1, sw2 = self.__card.transmit(apdu)
            except Exception as e:
                raise Exception("APDU transmission error after reconnect: " + str(e))

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

    def open_secure_channel(self, shared: bytes, nonce: bytes, token: bytes, pbkeyBytes: bytes):
        sc = SecureChannel(shared=shared, nonce=nonce)
        res = sc.verify_token(token, pbkeyBytes)
        if (not res):
            raise Exception('Secure Channel token verification failed')
        self.__sc = sc

    def select_applet(self, rescue : bool = False):
        if (rescue):
            return self.transmit([0x00, 0xA4, 0x04, 0x04, 0x08, 0xA0, 0x58, 0x3F, 0xC1, 0x9B, 0x7E, 0x4F, 0x21, 0x00])
        return self.transmit([0x00, 0xA4, 0x04, 0x00, 0x0B, 0xE8, 0x2B, 0x06, 0x01, 0x04, 0x01, 0x81, 0xC3, 0x1F, 0x02, 0x01, 0x00])

    def phy(self, data : Optional[list[int]] = None):
        if (data is None):
            try:
                resp, sw = self.send(0x1E, cla=0x80, p1=0x00, ne=256)
                return PhyData.parse(resp)
            except Exception:
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

    def secure_boot(self, bootkey_index: int = 0, lock: bool = False):
        data = bytes([bootkey_index & 0xFF, 1 if lock else 0])
        self.send(0x1C, cla=0x80, p1=0x02, data=data)
