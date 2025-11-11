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

import usb.core
import usb.util
from .ICCD import ICCD

class RescuePicoKey:

    def __init__(self):

        class find_class(object):
            def __init__(self, class_):
                self._class = class_
            def __call__(self, device):
                if device.bDeviceClass == self._class:
                    return True
                for cfg in device:
                    intf = usb.util.find_descriptor(cfg, bInterfaceClass=self._class)
                    if intf is not None:
                        return True
                return False

        devs = usb.core.find(find_all=True, custom_match=find_class(0x0B))
        found = False
        for dev in devs:
            if (dev.manufacturer == 'Pol Henarejos'):
                dev.set_configuration()
                cfg = dev.get_active_configuration()
                for intf in cfg:
                    if (intf.bInterfaceClass == 0xFF):
                        epin,epint = None,None
                        epo = usb.util.find_descriptor(intf, find_all=True, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
                        epi = usb.util.find_descriptor(intf, find_all=True, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
                        for ep in list(epi):
                            if (usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR):
                                epint = ep
                            else:
                                epin = ep
                        epout = list(epo)
                        self.__dev = dev
                        self.__in = epin.bEndpointAddress
                        self.__out = epout[0].bEndpointAddress
                        self.__int = epint.bEndpointAddress if epint else None
                        self.__iccd = ICCD(self)
                        self.__active = None
                        self.powerOff()
                        found = True
                        break
        if (not found):
            raise Exception('Not found any Pico Key device')

    def __str__(self):
        return str(self.__dev)

    def read(self, timeout=2000):
        ret = self.__dev.read(self.__in, 4096, timeout)
        return ret

    def write(self, data, timeout=2000):
        assert(self.__dev.write(self.__out, data, timeout) == len(data))

    def exchange(self, data, timeout=2000):
        self.write(data=data, timeout=timeout)
        return self.read(timeout=timeout)

    def powerOn(self):
        if (not self.__active):
            self.__active = True
            return self.__iccd.IccPowerOn()

    def powerOff(self):
        if (self.__active or self.__active is None):
            self.__iccd.IccPowerOff()
            self.__active = False

    def transmit(self, apdu):
        if (not self.__active):
            self.powerOn()
        rapdu = self.__iccd.SendApdu(apdu=apdu)
        return rapdu[:-2], rapdu[-2], rapdu[-1]
