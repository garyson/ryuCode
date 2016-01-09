__author__ = 'root'

from ryu.cfg import CONF
import logging
import time
import datetime as dt
#from ryu.app.domain_controller import DomainController

from ryu.app.domain_task import DomainTask, TaskList
from ryu.app.queue_qos import QueueInfo
from ryu.ofproto import ether
from ryu.exception import RyuException

DOMAINID = 'domainId'
TYPE = 'type'
PATHTYPE = 'pathType'
TASK_ID = 'taskId'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
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
NEXTHOP = 'nexthop'
SINGLESWITCH = 1


class DomainReplyController(object):

    def __init__(self):

        self.name = 'DomainReplyController'
        self.jsonMsg = None
        self.resetPriority = 0x8001
        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)

        self.logger.info("I am reply controller")

    def taskAssign(self, jsonMsg, DC, priority=None):

        assert jsonMsg[TYPE] == 'taskAssign'
        print jsonMsg
        self.jsonMsg = jsonMsg
        taskId = jsonMsg[TASK_ID]
        DC.taskId_match[taskId] = []
        #TASK_LIST = DC.TASK_LIST
        taskInstance = DC.TASK_LIST.setdefault(taskId, DomainTask(taskId))
        # taskInstance = DomainTask(taskId)
        pathType = jsonMsg[PATHTYPE]
        srcSwitch = jsonMsg[SRC_SWITCH]
        dstSwitch = jsonMsg[DST_SWITCH]
        srcIp = jsonMsg[SRC_IP]
        dstIp = jsonMsg[DST_IP]
        nexthop = jsonMsg[NEXTHOP]
        bandwidth = jsonMsg[BANDWIDTH]

        last_outport_num = jsonMsg[LAST_OUTPORT_NUM]
        if last_outport_num not in DC.port_to_localmac:
            local_mac = '00:00:00:00:00:01'
        else:
            local_mac = DC.port_to_localmac[last_outport_num]
        if nexthop in DC.local_mac:
            next_mac = DC.arp_table[dstIp]
        else:
            next_mac = DC.arp_table[nexthop]
            #next_mac = '00:00:00:00:00:02'
        # print 'DC.shortestPath: ',DC.shortestPath
        # print 'edgeport: ',DC.edgePort
        pathInfo = DC.shortestPath[(srcSwitch, dstSwitch)]
        PathList = jsonMsg[PARTPATH]

        labels = DC.LabelsPool.getLabels(len(pathInfo)-1)

        taskInstance.setFields(srcSwitch=srcSwitch, dstSwitch=dstSwitch, bandwidth=bandwidth,
                               path=PathList, labels=labels, pathType=pathType)

        #preSwitch = jsonMsg[PARTPATH]['pre']
        postSwitch = jsonMsg[PARTPATH]['post']
        switchList_from_super = taskInstance.getSwitchList(pathType)
        switchList = DC.shortestPath[tuple(switchList_from_super)]
        length = len(switchList)

        maxRate = taskInstance.getMaxRate()
        minRate = taskInstance.getMinRate()

        domainTopo = DC.topo
        DEVICEINFO = DC.deviceInfo

        # if priority is not None:
        #     DC.timeOfQos = 0
        #
        # if DC.timeOfQos == 0:
        #     DC.timeOfQos = 1


        for dpid in switchList:
            if dpid not in DC.qosSwitch:
                DC.qosSwitch.append(dpid)
                queueinstance = DC.QoS_dict[dpid]
                switchfeature = DEVICEINFO[dpid]
                ports = switchfeature.getPorts()
                for portNo in ports:
                        for queueId in range(1, 9):
                            queueinstance.queueInfo[portNo].queueList[queueId] = QueueInfo(maxRate, minRate)

                # used for testing QoS queue
                # if dpid == 518:
                #     for portNo in ports:
                #         for queueId in range(1, 9):
                #             queueinstance.queueInfo[portNo].queueList[queueId] = QueueInfo(maxRate, minRate)
                # else:
                #     for portNo in ports:
                #         queueinstance.queueInfo[portNo].queueList[1] = QueueInfo(maxRate, minRate)

        try:
            if length != 1:
                self.moredpid_handler(DEVICEINFO,switchList,domainTopo,DC,labels,
                                  maxRate,minRate,srcIp,dstIp,pathType,length,
                                  postSwitch,last_outport_num,local_mac,next_mac,
                                  taskId,priority)
            else:
                i = switchList[0]
                self.onedpid_handler(DEVICEINFO,postSwitch,DC,domainTopo,i,maxRate, minRate,srcIp,
                                 dstIp,pathType,last_outport_num,local_mac, next_mac,taskId,priority)

        except qosIdException:
            return

        DC.sendTaskAssignReply(taskId, pathType, srcSwitch, dstSwitch)
        self.jsonMsg = None


    def moredpid_handler(self,DEVICEINFO,switchList,domainTopo,DC,labels,
                                  maxRate,minRate,srcIp,dstIp,pathType,length,
                                  postSwitch,last_outport_num,local_mac,next_mac,taskId,priority):
        for i in switchList:
            index = switchList.index(i)
            if index == 0:
                self.task_assign_firstdpid(switchList,index,domainTopo,i,DC,labels,maxRate,minRate,srcIp,
                              dstIp,pathType,DEVICEINFO,local_mac,next_mac,taskId,priority)

            elif index == length - 1:
                self.lastdpid_handler(postSwitch,DC,domainTopo,i,maxRate, minRate,
                        last_outport_num,local_mac, next_mac,labels,DEVICEINFO,taskId,priority)

            else:
                nextSwitch = switchList[index + 1]
                outPortNo = domainTopo.getLinkOutPort(i, nextSwitch)
                self.task_assign_middpid(DC,i,outPortNo, maxRate, minRate,labels,index,DEVICEINFO,taskId,priority)


    def onedpid_handler(self,DEVICEINFO,postSwitch,DC,domainTopo,dpid,maxRate, minRate,srcIp,
                                 dstIp,pathType,last_outport_num,local_mac, next_mac,taskId,priority):

        nextSwitch = postSwitch
        if nextSwitch != 0:
            outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
            self.task_assign_onedpid(DC,outPortNo,dpid,maxRate,minRate,srcIp,dstIp,pathType,DEVICEINFO,taskId,priority)
        else:
            outPortNo = last_outport_num
            self.task_assign_onedpid_nopost(DC,dpid,outPortNo, maxRate, minRate,srcIp,
                                   dstIp,local_mac, next_mac,pathType,DEVICEINFO,taskId,priority)


    def lastdpid_handler(self,postSwitch,DC,domainTopo,dpid,maxRate, minRate,
                        last_outport_num,local_mac, next_mac,labels,DEVICEINFO,taskId,priority):
        nextSwitch = postSwitch
        if nextSwitch != 0:
            outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
            self.task_assign_lastdpid_to_3l(outPortNo,DC,dpid,
                              maxRate, minRate,labels,DEVICEINFO,taskId,priority)
        else:
            # raise ValueError("can not find out port, I think you should input a specify port no")
            outPortNo = last_outport_num
            self.task_assign_lastdpid_to_2l(outPortNo,DC,dpid,local_mac, next_mac,
                              maxRate, minRate,labels,DEVICEINFO,taskId,priority)


    def qos_set(self,DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO):
        switchInfo = DEVICEINFO[dpid]
        outPortName = switchInfo.getPortName(outPortNo)

        queueQosInstance = DC._get_QueueQos(dpid)
        queueId = queueQosInstance.get_queueid(outPortNo)

        if queueId == -1:
            self.logger.info("No more queue in this port, please change to another path")
            nextdpid = DC.topo.getNextDpid(outPortNo, dpid)
            DC.changeToBackPath(dpid, nextdpid)
            DC.sendPathChangeReply(dpid, nextdpid)
            self.taskAssign(self.jsonMsg, DC, self.resetPriority)
            raise qosIdException()
            # DC.stop()

        rest = queueQosInstance.make_queue_rest(outPortName, maxRate, minRate, queueId)

        queueQosInstance.queueInfo[outPortNo].queueList[queueId].changeIntoInUse()

        #ovs_bridge = DC.QoS_dict[dpid]
        status, msg = queueQosInstance.set_queue(rest)
        if status:
            self.logger.debug(msg)
            DC.stop()
        else:
            self.logger.info(msg)
        return queueId


    def task_assign_firstdpid(self,switchList,index,domainTopo,dpid,DC,labels,maxRate,minRate,srcIp,
                              dstIp,pathType,DEVICEINFO,src_mac,dst_mac,taskId,priority):
        nextSwitch = switchList[index + 1]
        outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        pushLabel = labels[index]
        match, mod = DC.pushMplsFlow(dpid, pushLabel,srcIp,dstIp,outPortNo,queueId,pathType,src_mac,dst_mac,priority)
        DC.taskId_match[taskId].append({dpid: match})

    def task_assign_lastdpid_to_2l(self,outPortNo,DC,dpid,local_mac, next_mac,
                              maxRate, minRate,labels,DEVICEINFO,taskId,priority):
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        popLabel = labels[-1]
        match, mod = DC.popMplsMacFlow(dpid, popLabel, outPortNo, local_mac, next_mac, queueId, priority)
        DC.taskId_match[taskId].append({dpid: match})

    def task_assign_lastdpid_to_3l(self,outPortNo,DC,dpid,
                              maxRate, minRate,labels,DEVICEINFO,taskId,priority):
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        popLabel = labels[-1]
        match, mod = DC.popMplsFlow(dpid, popLabel, outPortNo, queueId, priority)
        DC.taskId_match[taskId].append({dpid: match})

    def task_assign_middpid(self,DC,dpid,outPortNo, maxRate, minRate,labels,index,DEVICEINFO,taskId,priority):
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        pushLabel = labels[index]
        popLabel = labels[index - 1]
        match, mod =DC.swapMplsFlow(dpid, pushLabel, popLabel, outPortNo, queueId, priority)
        DC.taskId_match[taskId].append({dpid: match})

    def task_assign_onedpid(self,DC,outPortNo,dpid,maxRate, minRate,srcIp, dstIp,pathType,DEVICEINFO,taskId,priority):
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        match, mod = DC.noMplsFlow(dpid, srcIp, dstIp, outPortNo, queueId, pathType, priority)
        DC.taskId_match[taskId].append({dpid: match})

    def task_assign_onedpid_nopost(self,DC,dpid,outPortNo, maxRate, minRate,srcIp,
                                   dstIp,local_mac, next_mac,pathType,DEVICEINFO,taskId,priority):
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        match, mod = DC.noMplsMacFlow(dpid, srcIp, dstIp, outPortNo, local_mac, next_mac, queueId, pathType, priority)
        DC.taskId_match[taskId].append({dpid: match})

    def startBackup(self, jsonMsg, DC):
        assert jsonMsg[TYPE] == 'startBackup'
        assert jsonMsg[DOMAINID] == DC.domainId
        taskId = jsonMsg[TASK_ID]
        taskInstance = DC.TASK_LIST[taskId]
        # taskInstance = DomainTask(taskId)

        main_ = taskInstance.mainPath
        backup_ = taskInstance.backupPath

        if main_:
            mainList = taskInstance.getSwitchList('main')
            if backup_:
                backupList = taskInstance.getSwitchList('backup')
                if mainList[0] == backupList[0]:
                    switch = backupList[0]
                    mod = taskInstance.getBackupMod()
                    datapath = DC._get_datapath(switch)
                    datapath.send_msg(mod)
                    for i in range(1, len(mainList)):
                        switch = mainList[i]
                        match = taskInstance.getMainMatchInfo(switch)
                        datapath = DC._get_datapath(switch)
                        newMatch = self._get_new_match(datapath, match)
                        DC.remove_flow(datapath, newMatch)
                    taskInstance.changeBackupToMain()
                else:
                    mod = taskInstance.getBackupMod()
                    switch =backupList[0]
                    datapath = DC._get_datapath(switch)
                    datapath.send_msg(mod)
                    for switch in mainList:
                        match = taskInstance.getMainMatchInfo(switch)
                        datapath = DC._get_datapath(switch)
                        newMatch = self._get_new_match(datapath, match)
                        DC.remove_flow(datapath, newMatch)
                    taskInstance.changeBackupToMain()
            else:
                for switch in mainList:
                    match = taskInstance.getMainMatchInfo(switch)
                    datapath = DC._get_datapath(switch)
                    newMatch = self._get_new_match(datapath, match)
                    DC.remove_flow(datapath, newMatch)

                del DC.TASK_LIST[taskId]


        elif backup_:
            mod = taskInstance.getBackupMod()
            datapath = DC._get_datapath(taskInstance.getSwitchList('backup')[0])
            datapath.send_msg(mod)
            taskInstance.changeBackupToMain()

    def _get_new_match(self, datapath, match):
        newMatch = datapath.ofproto_parser.OFPMatch()
        newMatch._fields2 = match._fields2
        return newMatch

    def taskDelete(self, jsonMsg, DC):
        assert jsonMsg[TYPE] == 'taskDelete'

        taskId = jsonMsg[TASK_ID]
        assert taskId in DC.TASK_LIST

        taskInstance = DC.TASK_LIST[taskId]
        #taskInstance = DomainTask(1)

        main_ = taskInstance.mainPath
        backup_ = taskInstance.backupPath

        if main_:
            #mainList = taskInstance.getSwitchList('main')
            mainList = DC.taskId_match[taskId]
            src = mainList[0].keys()[0]
            dst = mainList[-1].keys()[0]
            for switch in mainList:
                #matchInfo = taskInstance.getMainMatchInfo(switch)
                datapath = DC._get_datapath(switch.keys()[0])
                matchInfo = switch.values()[0]
                newMatch = self._get_new_match(datapath, matchInfo)
                DC.remove_flow(datapath, newMatch)


        if backup_:
            backupList = taskInstance.getSwitchList('backup')
            for switch in backupList:
                matchInfo = taskInstance.getBackupMatchInfo(switch)
                datapath = DC._get_datapath(switch)
                newMatch = self._get_new_match(datapath, matchInfo)
                DC.remove_flow(datapath, newMatch)


        DC.sendTaskDeleteReply(taskId, src, dst)

class qosIdException(RyuException):
    message = 'qosId is not enough'




