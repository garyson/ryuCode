__author__ = 'hyq'

import eventlet
import json
eventlet.monkey_patch()

import logging
import sys
log = logging.getLogger()
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)

from ryu.services.protocols.bgp.bgpspeaker import BGPSpeaker

if __name__ == "__main__":
    speaker = BGPSpeaker(as_number=64512, router_id='10.0.0.1',
                         ssh_console=True)

    while True:
         eventlet.sleep(5)