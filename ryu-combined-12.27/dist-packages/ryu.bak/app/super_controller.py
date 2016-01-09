__author__ = 'root'

import networkx as nx
import json
import logging
import time
import os
import copy

from ryu.app.net import Task
from ryu.app.topo import TopoInfo
from ryu.app.labelsManager import MplsLabelsPool
from ryu.app.taskManager import TaskPool
from ryu.app.domainInfo import DomainInfo, SwitchInfo

from webob import Response
from ryu.app.wsgi import ControllerBase, WSGIApplication
from ryu.app.wsgi import route
from ryu.base import app_manager
from ryu.app.net import TASK_DICT, delTask, REQ_LIST, assertTaskInDict, getTask, registerTask

from ryu.app.super_reply_controller import SuperReplyController
from ryu.lib import hub



SUPERCONTROLLER = 'SuperController'
SUPERREPLYCONTROLLER = 'SuperReplyController'

SUPERBASEURL = '/super'
DOMAINURLNORETURN = '/domain/noreturn'
DOMAINURLRETURN = '/domain/return'


DOMAINID = 'domainId'
TYPE = 'type'
PATHTYPE = 'pathType'
TASK_ID = 'taskId'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
SRC_MAC = 'srcMac'
DST_MAC = 'dstMac'
SRC_SWITCH = 'srcSwitch'
DST_SWITCH = 'dstSwitch'
BANDWIDTH = 'bandwidth'
PARTPATH = 'path'
LABELS = 'labels'
DOMAINWSGIIP = 'domainWsgiIp'
DOMAINWSGIPORT = 'domainWsgiPort'
NEXT_MAC = 'next_mac'
LOCAL_MAC = 'local_mac'
LAST_OUTPORT_NUM = 'last_outport_num'
# TYPE = 'Type'
DOMAINTYPE = 'domain_type'


class SuperController(app_manager.RyuApp):

    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SuperController, self).__init__(*args, **kwargs)

        self.wsgiIp = '10.108.90.200'
        self.wsgiPort = 8080
        ##################################################
        self.topo = TopoInfo()
        self.trafficBalance = True
        ######################################
        self.virualTopo = TopoInfo()

        ##################################################
        self.LabelsPool = MplsLabelsPool()
        self.LabelsPool.initPool()
        ##################################################
        self.domains = {}

        ###################################################
        self.table = Table
        #self.domaintype = {'L3':[1],'L2':[2]}
        wsgi = kwargs['wsgi']

        data = {}
        data[SUPERCONTROLLER] = self
        data[SUPERREPLYCONTROLLER] = SuperReplyController()

        #self.keepalivethread = hub.spawn(self._keep_alive())

        wsgi.register(SuperWsgiController, data)
        # self.newtaskThreadFlag = self.CONF.newtask_thread_flag
        # if self.newtaskThreadFlag:
        #self.keepalivethread = hub.spawn(self._keep_alive())


    def startBackupHandler(self, taskId):
        taskInstance = getTask(taskId)
        backupPathDomains = taskInstance.getBackupCrossDomains()
        if not backupPathDomains:
            self.logger.info('NO Backup Path for this Task')
            return

        mainPathDomains = taskInstance.getMainCrossDomains()

        handlerDomains = self._add_diff_from_list(backupPathDomains, mainPathDomains)

        for domainId in handlerDomains:
            self.sendStartBackupPathMsg(domainId, taskId)

        taskInstance.changeBackupToMain()

    def _add_diff_from_list(self, list1, list2):
        list_ = []
        for i in list1:
            list_.append(i)

        for j in list2:
            if j not in list_:
                list_.append(j)

        return list_

    def sendStartBackupPathMsg(self, domainId, taskId):
        send_message = self._make_start_backup_msg(domainId, taskId)
        command = self._to_commad(send_message)
        # print "start backup: ", command
        self.send_no_return_command(command)

    def _make_start_backup_msg(self, domainId, taskId):

        to_send = {}
        to_send[TYPE] = 'startBackup'
        to_send[DOMAINID] = domainId
        to_send[TASK_ID] = taskId

        send_message = json.dumps(to_send)
        return send_message

    def setNewBackupPath(self, taskId):
        taskInstance = getTask(taskId)
        completePathMain = taskInstance.getMainCompletePath()
        assert len(completePathMain) > 1  # to make sure we set a backupPath for a task having a mainPath
        mainEdges = taskInstance.getMainEdges()
        newTopo = self.topo.getNewTopoExceptSE(mainEdges)

        srcSwitch = taskInstance.getSrcSwtich()
        dstSwtich = taskInstance.getDstSwitch()

        if self.trafficBalance:
            newCompletePathBackup = newTopo.getWeightPath(srcSwitch, dstSwtich)
        else:
            newCompletePathBackup = newTopo.getShortestPath(srcSwitch, dstSwtich)

        if not newCompletePathBackup:
            self.logger.warning("can not assign a new backupPath for this task ")
            return

        taskInstance.setBackupCompletePath(newCompletePathBackup)
        nodeToDomain = self.topo.nodeToDomainId
        newBackupSectorialPath = taskInstance.getBackupSectorialPath(nodeToDomain)

        newAllBackupPathMpls = self.LabelsPool.getLabels(len(newCompletePathBackup))
        noUseLabels = taskInstance.assignBackuPathMpls(newAllBackupPathMpls)
        self.LabelsPool.recycleLabels(noUseLabels)

        for i in newBackupSectorialPath:
            send_message = taskInstance.makeDomainTaskAssign(i,  type='backup')
            command = self._to_commad(send_message)
            # print 'newbackup: ', command
            self.send_no_return_command(command)
            taskInstance.addBackupUnconfirmDomain(i)


    def _keep_alive(self):
        while True:
            for i in self.domains:
                self.sendKeepAlive(i)
                self.logger.info("send keepalive to domain %d" % i)
            hub.sleep(10)

    def sendKeepAlive(self, i):
        send_message = self._make_keep_alive(i)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)


    def _make_keep_alive(self, i):
        to_send = {}
        to_send[TYPE] = 'keepAlive'
        to_send[DOMAINID] = i

        send_message = json.dumps(to_send)
        return send_message


    def send_no_return_command(self, command):
        try:
            os.popen2(command)
        except:
            self.logger.debug('command exceute fail.Fail Command: %s' % command)
            return

    def _to_commad(self, send_message, returnType=False):

        message = eval(send_message)
        domainId = message.get(DOMAINID)
        domainInstance = self.domains.get(domainId)
        domainWsgiIp = domainInstance.getWsgiIp()
        domainWsgiPort = domainInstance.getWsgiPort()
        #different domainID different domain_instance
        command = 'curl -X '
        if returnType:
            command += 'GET -d \''
        else:
            command += 'PUT -d \''
        command += send_message
        command += '\' http://'
        command += domainWsgiIp
        command += ':'
        command += str(domainWsgiPort)
        if not returnType:
            command += DOMAINURLNORETURN
        else:
            command += DOMAINURLRETURN

        command += ' 2> /dev/null'
        #print 'command: ',command
        return command








class SuperWsgiController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(SuperWsgiController, self).__init__(req, link, data, **config)
        self.name = 'SuperWsgiController'
        self.SuperController = data[SUPERCONTROLLER]
        self.SuperReplyController = data[SUPERREPLYCONTROLLER]
        # self.newtaskThread = hub.spawn(self.newTask)


        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)

    @route('super', SUPERBASEURL + '/noreturn', methods=['PUT'], requirements=None)
    def noreturned_command_handler(self, req):
        msgbody = eval(req.body)
        assert TYPE in msgbody
        type = msgbody.get(TYPE, None)
        if not type:
            self.logger.fatal("Not type in msgbody")
            return

        try:
            func = getattr(self.SuperReplyController, type)
#            if type is 'ArpMessage':
#                func(msgbody, self.SuperController, Table)
        except:
            self.logger.fatal('can not find handler')
            return

        func(msgbody, self.SuperController)

    @route('super','/super/test',methods=['GET'],requirements=None)
    def test(self,req):


        a = {TYPE: 123}
        qwe = json.dumps(a)
        command = 'curl -X PUT -d \'' + qwe + '\' http://10.108.90.202:8080/domain/test1'
        # print command
        os.popen(command)
        print 'this is a test!'


    @route('super', SUPERBASEURL + '/return', methods=['PUT'], requirements=None)
    def returned_command_handler(self, req):
        msgbody = eval(req.body)
        assert TYPE in msgbody
        type = msgbody.get(TYPE, None)
        if not type:
            self.logger.fatal("Not type in msgbody")
            return

        try:
            func = getattr(self.super_reply_controller, type)
        except:
            self.logger.error('Can not find handler')
            return

        func(msgbody, self.SuperController)


    # @route('super', SUPERBASEURL + '/task/assign', methods=['PUT'], requirements=None)
    #curl -X PUT -d '{TYPE:"newtask"}' http://127.0.0.1:8080/super/newtask
    @route('super', SUPERBASEURL + '/newtask', methods=['PUT'], requirements=None)
    def newTask(self, req):

        SC = self.SuperController
        body = req.body
        rest = eval(body)
        assert TYPE in rest
        type = rest.get(TYPE, None)
        if not type:
            self.logger.fatal("Not type in msgbody")
            return
        # typee = rest[TYPEE]
        # taskpoolinstance = TaskPool()
        self.TaskPool = TaskPool()
        self.TaskPool.initTaskPool()

        Peer_Table_ip = {(('10.108.92.0','255.255.255.0'), ('10.108.93.0','255.255.255.0')): self.SuperController.
            table.ip_return_src_and_dst_dpid('10.108.92.0/24','10.108.93.0/24'),
                         (('10.108.93.0','255.255.255.0'), ('10.108.92.0','255.255.255.0')): self.SuperController.
            table.ip_return_src_and_dst_dpid('10.108.93.0/24','10.108.92.0/24')}
                                                                #src_dpid,dst_dpid,dst_port,dst_mac
        # Peer_Table_ip = {(('10.108.92.0','255.255.255.0'), ('10.108.93.0','255.255.255.0')): (513,518,34,'40:8d:5c:37:1f:b5'),
        #               (('10.108.93.0','255.255.255.0'), ('10.108.92.0','255.255.255.0')): (518,513,4,'f4:4e:05:9a:e0:c0')}
        # print Peer_Table_ip
        peer_table_mac = {('c8:9c:dc:7a:6d:7a','00:00:00:00:00:01'):self.SuperController.
            table.mac_to_src_dst_dpid('c8:9c:dc:7a:6d:7a','00:00:00:00:00:01'),
                          ('00:00:00:00:00:01','c8:9c:dc:7a:6d:7a'):self.SuperController.
            table.mac_to_src_dst_dpid('00:00:00:00:00:01','c8:9c:dc:7a:6d:7a')}
        # print peer_table_mac
                                                                    #src_dpid,dst_dpid,dst_port
        # peer_table_mac = {('c8:9c:dc:7a:6d:7a','00:00:00:00:00:01'): (769,773,25),
        #                   ('00:00:00:00:00:01','c8:9c:dc:7a:6d:7a'): (773,769,4)}


        #curl -X PUT -d '{TYPE: "newtask"}' http://0.0.0.0:8080/super/newtask


        peer_table1 = copy.copy(Peer_Table_ip)
        peer_table2 = copy.copy(peer_table_mac)
        #self.sleep = 120
        #hub.sleep(self.sleep)


        #two paths and two task_assign
        for s_d in peer_table1.keys():
            if s_d:
                request = {SRC_SWITCH: peer_table1[s_d][0],
                       DST_SWITCH: peer_table1[s_d][1],
                       LAST_OUTPORT_NUM: peer_table1[s_d][2],
                       SRC_IP: s_d[0], DST_IP: s_d[1],
                       LOCAL_MAC: '00:00:00:00:00:00',
                       NEXT_MAC: peer_table1[s_d][3],
                       BANDWIDTH: {"peak": 5000000, "guranted": 2000000},
                       TASK_ID: self.TaskPool.get_taskid(),
                       DOMAINTYPE: 'L3'}

                REQ_LIST.append(request)

                self.taskAssign(str(request))
                self.logger.info("Build a path in L3 domain from %s to %s" %
                                 (request[SRC_SWITCH], request[DST_SWITCH]))

        for s_d in peer_table2.keys():
            if s_d:
                request = {SRC_SWITCH: peer_table2[s_d][0],
                       DST_SWITCH: peer_table2[s_d][1],
                       LAST_OUTPORT_NUM: peer_table2[s_d][2],
                       SRC_MAC: s_d[0], DST_MAC: s_d[1],
                       LOCAL_MAC: None,
                       NEXT_MAC: None,
                       BANDWIDTH: {"peak": 5000000, "guranted": 2000000},
                       TASK_ID: self.TaskPool.get_taskid(),
                       DOMAINTYPE: 'L2'}

                REQ_LIST.append(request)

                self.taskAssign(str(request))
                self.logger.info("Build a path in L2 domain from %s to %s" %
                                 (request[SRC_SWITCH], request[DST_SWITCH]))


    def taskAssign(self, req):

        SC = self.SuperController
        body = req
        #print repr(req)
        rest = eval(body)
        taskId = rest[TASK_ID]

        if not taskId:
            return Response(status=200, body="there is no task Id\n")

        #if taskid and task object have been registered,return a task object ,or instantiate a task object
        if assertTaskInDict(taskId):
            taskInstance = getTask(taskId)
        else:
            taskInstance = Task(taskId)


        if taskInstance.isEstablished():
            
            return Response(status=200, body="taskId duplicated!\n")

        srcSwitch = rest[SRC_SWITCH]
        dstSwitch = rest[DST_SWITCH]
        bandwith = rest[BANDWIDTH]
        # duration = rest[]
        local_mac = rest[LOCAL_MAC]
        next_mac = rest[NEXT_MAC]
        last_outport_num = rest[LAST_OUTPORT_NUM]

        domain_type = rest[DOMAINTYPE]

        if domain_type is 'L3':
            dstIp = rest[DST_IP]
            srcIp = rest[SRC_IP]
            taskInstance.taskSetIpFields(srcSwitch=srcSwitch, dstSwitch=dstSwitch, srcIp=srcIp, dstIp=dstIp,
                                   local_mac=local_mac, next_mac=next_mac, last_outport_num=last_outport_num,
                                   bandwidth=bandwith)
        #generate a task object
        else:
            srcMac = rest['srcMac']
            dstMac = rest['dstMac']
            #print 'srcMac,dstMac: ',srcMac,dstMac
            taskInstance.taskSetMacFields(srcSwitch=srcSwitch, dstSwitch=dstSwitch, srcMac=srcMac,dstMac=dstMac,
                                      last_outport_num=last_outport_num,bandwidth=bandwith)
##########################################################################################################
        #print 'SC.virualTopo.topo.edges(): ',SC.virualTopo.topo.edges()
        #print 'srcSwitch,dstSwitch: ',srcSwitch,dstSwitch
        completePathVir = SC.virualTopo.getWeightPath(int(srcSwitch), int(dstSwitch))
        # print 'New Task src_dpid,dst_dpid: ',srcSwitch,dstSwitch
        # print 'New Task completePathVir: ', completePathVir
        # print 'New Task topo: ',SC.virualTopo.edges()
        #print 'topo: ',SC.virualTopo.edge()



        if not completePathVir:
            self.logger.warning("no virual path between switch %0x16 and %0x16" % (srcSwitch, dstSwitch))
            return Response(status=200, body="no main path between switch %0x16 and %0x16\n" % (srcSwitch, dstSwitch))
        print "Link calculate success between %0x16 and %0x16:"%(int(srcSwitch), int(dstSwitch)),completePathVir

        # allMainPathMpls = SC.LabelsPool.getLabels(len(completePathVir))#n different numbers
        # noUseLabels = taskInstance.assignMainPathMpls(allMainPathMpls)
        # SC.LabelsPool.recycleLabels(noUseLabels)

        taskInstance.setVirCompletePath(completePathVir)
        virEdges = taskInstance.getVirEdges()
        # print 'virEdges: ',virEdges
        nodeToDomain = SC.topo.nodeToDomainId
        virSectorialPath = taskInstance.getVirSectorialPath(nodeToDomain, virEdges)

        # print 'virSectorialPath: ', virSectorialPath

        registerTask(taskInstance)
        print "Begin send task to Domain."
        for i in virSectorialPath:
            send_message = taskInstance.makeDomainTaskAssign(i)
            # print 'send_message: ', send_message
            command = SC._to_commad(send_message)
            # print "main: ", command
            SC.send_no_return_command(command)
            taskInstance.addMainUnconfirmDomain(i)
############################################################################################
        # load balance----weightpath,or shortestpath
        # if SC.trafficBalance:#set main and back paths in the task
        #     print (srcSwitch,dstSwitch)
        #     #print SC.topo.__dict__
        #     completePathMain = SC.topo.getWeightPath(srcSwitch, dstSwitch)
        #     print 'pathmain: ', completePathMain#completepathmain is a list including dpids
        #                                         #dpid is a 0x number
        #
        #     if not completePathMain:
        #         self.logger.warning("no main path between switch %d and %d" % (srcSwitch, dstSwitch))
        #         return Response(status=200, body="no main path between switch %d and %d\n" % (srcSwitch, dstSwitch))
        #
        #     taskInstance.setMainCompletePath(completePathMain)
        #     mainEdges = taskInstance.getMainEdges()#mainedges is a tuple list which includes paths
        #
        #     newTopo = SC.topo.getNewTopoExceptSE(mainEdges)
        #     completePathBackup = newTopo.getWeightPath(srcSwitch, dstSwitch)
        #     if not completePathBackup:
        #         self.logger.warning("no backup path between switch %d and %d" % (srcSwitch, dstSwitch))
        #
        #     taskInstance.setBackupCompletePath(completePathBackup)
        #
        #
        # else:
        #     completePathMath = SC.topo.getShortestPath(srcSwitch, dstSwitch)
        #     if not completePathMath:
        #         self.logger.warning("no main path between switch %d and %d" % (srcSwitch, dstSwitch))
        #         return Response(status=200, body="no main path between switch %d and %d\n" % (srcSwitch, dstSwitch))
        #
        #     taskInstance.setMainCompletePath(completePathMath)
        #     mainEdges = taskInstance.getMainEdges()
        #     newTopo = SC.topo.getNewTopoExceptSE(mainEdges)
        #     completePathBackup = newTopo.getShorestPath(srcSwitch, dstSwitch)
        #     if not completePathBackup:
        #         self.logger.warning("no backup path between switch %d and %d" % (srcSwitch, dstSwitch))
        #
        #     taskInstance.setBackupCompletePath(completePathBackup)




        # nodeToDomain = SC.topo.nodeToDomainId
        # mainSectorialPath = taskInstance.getMainSectorialPath(nodeToDomain)
        #backupSectorialPath = taskInstance.getBackupSectorialPath(nodeToDomain)
        # print mainSectorialPath
        #{1: {'list': [9120431834591789832L, 514, 517]}, 2: {'list': [773, 770, 2770919309952811793L]}}

        # allMainPathMpls = SC.LabelsPool.getLabels(len(completePathMain))#n different numbers
        # noUseLabels = taskInstance.assignMainPathMpls(allMainPathMpls)
        # SC.LabelsPool.recycleLabels(noUseLabels)

        # allBackupPathMpls = SC.LabelsPool.getLabels(len(completePathBackup))
        # noUseLabels = taskInstance.assignBackuPathMpls(allBackupPathMpls)
        # SC.LabelsPool.recycleLabels(noUseLabels)



        #registerTask(taskInstance)
        # print "main: ", completePathMain
        # print "backup: ", completePathBackup
        # print "nodeToDomain: ", nodeToDomian

        # for i in mainSectorialPath:
        #     send_message = taskInstance.makeDomainTaskAssign(i)
        #     #makedomaintaskassign() return a dict 'to_send' which contains paths
        #     command = SC._to_commad(send_message)
        #     print "main: ", command
        #     SC.send_no_return_command(command)
        #
        #     taskInstance.addMainUnconfirmDomain(i)

        

        # for j in backupSectorialPath:
        #     send_message = taskInstance.makeDoaminTaskAssign(j, type='backup')
        #
        #     command = SC._to_commad(send_message)
        #     print "backup: ",command
        #     SC.send_no_return_command(command)
        #     taskInstance.addBackupUnconfirmDomain(j)


    @route('super', SUPERBASEURL + '/task/delete', methods=['PUT'], requirements=None)
    def taskDelete(self, req):

        SC = self.SuperController
        rest = eval(req)

        taskId = rest[TASK_ID]
        if not assertTaskInDict(taskId):
            self.logger.info("no task %d" % taskId)
            return Response(status=200, body='No task %d\n' % taskId)

        taskInstance = getTask(taskId)
        allCrossDomains = taskInstance.getAllDomains()
        taskInstance.setDeleteDomains(allCrossDomains)
        for i in allCrossDomains:
            send_message = taskInstance.makeTaskDeleteMsg(i)
            command =SC._to_commad(send_message)
            SC.send_no_return_command(command)


class table(object):

    _instance = None


    @staticmethod
    def get_instance():
        if not table._instance:
            table._instance = table()
        return table._instance

    def __init__(self):

#'10.108.92.0/24':'f4:4e:05:9a:e0:c0','10.108.91.0/24':'00:10:01:08:00:03'
#'10.108.92.0/24':'4','10.108.91.0/24':'6'


        self.ip_to_mac = {'10.108.93.100': '00:00:00:00:00:01', '10.108.93.101': '00:00:00:00:00:02'}
        self.ip_to_port = {'10.108.93.100': 34, '10.108.93.101': 11}
        self.ip_to_dpid = {'10.108.93.100': 518, '10.108.93.101': 518}
        self.port_to_localmac = {}
#        self.port_to_dpid = {}
#        self.dpid_to_localmac = {}


        self.arp_extension_table = {}
#mac_to_port = {'518': {'48:6e:73:02:03:08': 31}, '513': {'48:6e:73:02:03:08': 3, 'bc:67:1c:02:8a:01': 5},
# '515': {'48:6e:73:02:03:08': 15, 'bc:67:1c:02:8a:01': 13}}
        self.mac_to_port = {773: {'00:00:00:00:00:01': 25}}
        self.mac_to_dpid = {'00:00:00:00:00:01': 773}

        self.prefix_to_nexthop = {'10.108.93.0/24': '10.108.93.100'}



    def ip_return_src_and_dst_dpid(self,src_ip,dst_ip):
        nexthop1 = self.prefix_to_nexthop.get(src_ip, None)
        nexthop2 = self.prefix_to_nexthop.get(dst_ip, None)

        src_dpid = self.ip_to_dpid.get(nexthop1, None)
        dst_dpid = self.ip_to_dpid.get(nexthop2, None)

        dst_port = self.ip_to_port.get(nexthop2, None)
        dst_mac = self.ip_to_mac.get(nexthop2, None)

        return (src_dpid, dst_dpid, dst_port, dst_mac)


    def mac_to_src_dst_dpid(self,src_mac,dst_mac):
        #print 'src_mac,dst_mac: ',src_mac,dst_mac
        src_dpid = self.mac_to_dpid.get(src_mac,None)
        #print 'src_dpid: ',src_dpid
        dst_dpid = self.mac_to_dpid.get(dst_mac,None)
        # print 'dst_dpid: ', dst_dpid, 'mac_to_port: ', self.mac_to_port
        dst_port = self.mac_to_port[dst_dpid][dst_mac]
        return (src_dpid,dst_dpid,dst_port)


    def mac_to_dpid1(self):
        for i in self.mac_to_port.keys():
            tmp = self.mac_to_port[i].keys()
            for j in tmp:
                self.mac_to_dpid[j] = i


Table = table.get_instance()







