__author__ = 'hyq'

import eventlet
#BGPspeaker needs sockets patched
eventlet.monkey_patch()

#initialize a log handler
#this is not strictly necessary but useful if you get message like:
#no handlers could be found for logger "ryu,lib.hub"

import logging
import sys
log = logging.getLogger()
log.addHandler(logging.StreamHandler(sys.stderr))

import os
from ryu.controller import event
import json

from ryu.services.protocols.bgp.bgpspeaker import BGPSpeaker


def dump_remote_best_path_change(event):
    print 'the best path changed:', event.remote_as, event.prefix, event.nexthop
    BGPevent = bgpevent(event)
    ev_dict = object2dict(BGPevent)
    ev_dict['type'] = 'BGPMessage'
    send_msg = json.dumps(ev_dict)
    command = _to_commad(send_msg)
    send_no_return_command(command)

def detect_peer_down(remote_ip,remote_as):
    print 'Peer down:',remote_ip,remote_as

def object2dict(obj):
    d={}
    d['__class__'] = obj.__class__.__name__
    d['__module__'] = obj.__module__
    d.update(obj.__dict__)
    return d


def send_no_return_command(command):
    #print command
    os.popen2(command)


def _to_commad(send_message):

    command = 'curl -X '
    command += 'PUT -d \''
    command += send_message
    command += '\' http://'
    command += '127.0.0.1'
    command += ':'
    command += '8080'
    command += '/super/noreturn'
    command += ' 2> /dev/null'

    return command

class bgpevent(event.EventBase):
    def __init__(self,ev):
        self.remote_as = ev.remote_as
        self.prefix = ev.prefix
        self.nexthop = ev.nexthop


if __name__=="__main__":
    speaker = BGPSpeaker(as_number=20,router_id='1.1.1.2',
                         best_path_change_handler=dump_remote_best_path_change,
                         peer_down_handler=detect_peer_down
                         )
    #speaker.neighbor_add("10.108.90.1",10)
    #speaker.neighbor_add("10.108.91.1",30)
    speaker.neighbor_add("10.108.92.1",10)

    #uncomment the below line if the speaker needs to talk with a bmp server
    #speaker.bmp_server_add('192.168.177.2',11019)

    count=1
    while True:
        eventlet.sleep(10)
        prefix = ['10.108.93.0/24', '10.108.94.0/24']
        for i in prefix:
            print "add a new prefix", i
            speaker.prefix_add(i)
        count+=1
        if count == 10:
            speaker.shutdown()
            break


