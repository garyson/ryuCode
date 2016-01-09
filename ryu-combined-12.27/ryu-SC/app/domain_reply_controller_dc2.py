__author__ = 'root'

from ryu.cfg import CONF
import logging
import time
import datetime as dt

# from ryu.app.domain_controller import DomainController

from ryu.app.domain_task import DomainTask, TaskList
from ryu.app.queue_qos import QueueInfo
DOMAINID = 'domainId'
TYPE = 'type'
PATHTYPE = 'pathType'
TASK_ID = 'taskId'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
SRC_SWITCH = 'srcSwitch'
DST_SWITCH = 'dstSwitch'
SRC_MAC = 'srcMac'
DST_MAC = 'dstMac'
BANDWIDTH = 'bandwidth'
PARTPATH = 'path'
LABELS = 'labels'
DOMAINWSGIIP = 'domainWsgiIp'
DOMAINWSGIPORT = 'domainWsgiPort'
# NEXT_MAC = 'next_mac'  ##
# LOCAL_MAC = 'local_mac'
LAST_OUTPORT_NUM = 'last_outport_num'   ##

SINGLESWITCH = 1


class DomainReplyController(object):

    def __init__(self):

        self.name = 'DomainReplyController'

        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)

        self.logger.info("I am Domain reply controller")

    def taskAssign(self, jsonMsg, DC):

        assert jsonMsg[TYPE] == 'taskAssign'
        # DC = DomainController
        #print jsonMsg

        taskId = jsonMsg[TASK_ID]
        TASK_LIST = DC.TASK_LIST
        taskInstance = TASK_LIST.setdefault(taskId, DomainTask(taskId))
        # taskInstance = DomainTask(taskId)
        pathType = jsonMsg[PATHTYPE]
        srcSwitch = jsonMsg[SRC_SWITCH]
        dstSwitch = jsonMsg[DST_SWITCH]
        # srcIp = jsonMsg[SRC_IP]
        # dstIp = jsonMsg[DST_IP]
        srcMac = jsonMsg[SRC_MAC]
        dstMac = jsonMsg[DST_MAC]
        bandwidth = jsonMsg[BANDWIDTH]

        # print 'DC.edges: ',DC.edgePort
        # print 'DC.shortestPath: ',DC.shortestPath

        pathInfo = DC.shortestPath[(srcSwitch, dstSwitch)]
        PathList = jsonMsg[PARTPATH]
        # PathList = []
        # for node in pathInfo:
        #     PathList = pathInfo.setdefault('list', [])
        #     assert node not in PathList
        #     PathList.append(node)

        last_outport_num = jsonMsg[LAST_OUTPORT_NUM]

        labels = DC.LabelsPool.getLabels(len(pathInfo)-1)


        taskInstance.setFields(srcSwitch=srcSwitch, dstSwitch=dstSwitch, bandwidth=bandwidth,
                                path=PathList, labels=labels, pathType=pathType)

        switchList_from_super = taskInstance.getSwitchList(pathType)
        switchList = DC.shortestPath[tuple(switchList_from_super)]
        #preSwitch = jsonMsg[PARTPATH]['pre']
        postSwitch = jsonMsg[PARTPATH]['post']
        length = len(switchList)

        maxRate = taskInstance.getMaxRate()
        minRate = taskInstance.getMinRate()

        domainTopo = DC.topo
        DEVICEINFO = DC.deviceInfo

        
        for dpid in switchList:
            queueinstance = DC.QoS_dict[dpid]
            switchfeature = DEVICEINFO[dpid]
            ports = switchfeature.getPorts()
            for port in ports:
                for queueId in range(1,9):
                    queueinstance.queueInfo[port].queueList[queueId] = QueueInfo(maxRate,minRate)


        if length != 1:
            self.moredpid_handler(DEVICEINFO,switchList,domainTopo,DC,labels,
                                  maxRate,minRate,srcMac,dstMac,pathType,length,
                                  postSwitch,last_outport_num)
        else:
            i = switchList[0]
            self.onedpid_handler(DEVICEINFO,postSwitch,DC,domainTopo,i,maxRate, minRate,srcMac,
                                 dstMac,pathType,last_outport_num)

        DC.sendTaskAssignReply(taskId, pathType)


    def moredpid_handler(self,DEVICEINFO,switchList,domainTopo,DC,labels,
                                  maxRate,minRate,srcMac,dstMac,pathType,length,
                                  postSwitch,last_outport_num):
        for i in switchList:
            index = switchList.index(i)
            if index == 0:
                self.task_assign_firstdpid(switchList,index,domainTopo,i,DC,labels,maxRate,minRate,
                                           srcMac,dstMac,pathType,DEVICEINFO)

            elif index == length - 1:
                self.lastdpid_handler(postSwitch,DC,domainTopo,i,maxRate, minRate,
                        last_outport_num,labels,DEVICEINFO)

            else:
                nextSwitch = switchList[index + 1]
                outPortNo = domainTopo.getLinkOutPort(i, nextSwitch)
                # switchInfo = DEVICEINFO[i]
                # outPortName = switchInfo.getPortName(outPortNo)
                self.task_assign_middpid(DC,i,outPortNo, maxRate, minRate,labels,index,DEVICEINFO)


    def onedpid_handler(self,DEVICEINFO,postSwitch,DC,domainTopo,dpid,maxRate, minRate,srcIp,
                                 dstIp,pathType,last_outport_num):

        nextSwitch = postSwitch
        if nextSwitch != 0:
            outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
            #self.task_assign_onedpid(DC,outPortNo,dpid,maxRate, minRate,srcIp, dstIp,pathType,DEVICEINFO)
        else:
            outPortNo = last_outport_num
        self.task_assign_onedpid(DC,dpid,outPortNo, maxRate, minRate,srcIp,
                                   dstIp,pathType,DEVICEINFO)


    def lastdpid_handler(self,postSwitch,DC,domainTopo,dpid,maxRate, minRate,
                        last_outport_num,labels,DEVICEINFO):
        nextSwitch = postSwitch
        if nextSwitch != 0:
            outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
        else:
            # raise ValueError("can not find out port, I think you should input a specify port no")
            outPortNo = last_outport_num
        self.task_assign_lastdpid(outPortNo,DC,dpid,
                              maxRate, minRate,labels,DEVICEINFO)


    def qos_set(self,DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO):
        switchInfo = DEVICEINFO[dpid]
        print 'dpid,outputNo: ',dpid,outPortNo
        outPortName = switchInfo.getPortName(outPortNo)

        queueQosInstance = DC._get_QueueQos(dpid)
        queueId = queueQosInstance.get_queueid(outPortNo)
        if queueId == -1:
            self.logger.info("No more queue")
            #return
            DC.stop()
        rest = queueQosInstance.make_queue_rest(outPortName, maxRate, minRate, queueId)

        queueQosInstance.queueInfo[outPortNo].queueList[queueId].changeIntoInUse()

        ovs_bridge = DC.QoS_dict[dpid]
        status, msg = ovs_bridge.set_queue(rest)
        if status:
            self.logger.debug(msg)
            #return
            DC.stop()
        else:
            self.logger.info(msg)
        return queueId


    def task_assign_firstdpid(self,switchList,index,domainTopo,dpid,DC,labels,maxRate,minRate,srcMac,
                              dstMac,pathType,DEVICEINFO):
        nextSwitch = switchList[index + 1]
        outPortNo = domainTopo.getLinkOutPort(dpid, nextSwitch)
        # queueQosInstance = DC._get_QueueQos(dpid)
        # queueId = queueQosInstance.get_queueid(outPortNo, maxRate, minRate)
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        pushLabel = labels[index]

        match, mod = DC.pushMplsFlow(dpid, pushLabel, srcMac, dstMac, outPortNo, queueId, pathType)


    def task_assign_lastdpid(self,outPortNo,DC,dpid,
                              maxRate, minRate,labels,DEVICEINFO):

        # queueQosInstance = DC._get_QueueQos(dpid)
        # queueId = queueQosInstance.get_queueid(outPortNo, maxRate, minRate)
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        popLabel = labels[-1]
        match, mod = DC.popMplsFlow(dpid, popLabel, outPortNo,queueId)


    def task_assign_middpid(self,DC,dpid,outPortNo, maxRate, minRate,labels,index,DEVICEINFO):
        # queueQosInstance = DC._get_QueueQos(dpid)
        # queueId = queueQosInstance.get_queueid(outPortNo, maxRate, minRate)
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        pushLabel = labels[index]
        popLabel = labels[index - 1]
        match, mod = DC.swapMplsFlow(dpid, pushLabel, popLabel, outPortNo, queueId)


    def task_assign_onedpid(self,DC,outPortNo,dpid,maxRate,minRate,srcMac,dstMac,pathType,DEVICEINFO):
        # queueQosInstance = DC._get_QueueQos(dpid)
        # queueId = queueQosInstance.get_queueid(outPortNo, maxRate, minRate)
        queueId = self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
        match, mod = DC.noMplsFlow(dpid, srcMac, dstMac, outPortNo, queueId, pathType)


    # def task_assign_onedpid_nopost(self,DC,dpid,outPortNo, maxRate, minRate,srcMac,
    #                                dstMac,pathType,DEVICEINFO):
    #     queueQosInstance = DC._get_QueueQos(dpid)
    #     queueId = queueQosInstance.get_queueid(outPortNo, maxRate, minRate)
    #     self.qos_set(DC,outPortNo,dpid,maxRate,minRate,DEVICEINFO)
    #     match, mod = DC.noMplsMacFlow(dpid, srcMac, dstMac, outPortNo,queueId, pathType)


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
            mainList = taskInstance.getSwitchList('main')
            for switch in mainList:
                matchInfo = taskInstance.getMainMatchInfo(switch)
                datapath  =DC._get_datapath(switch)
                newMatch = self._get_new_match(datapath, matchInfo)
                DC.remove_flow(datapath, newMatch)


        if backup_:
            backupList = taskInstance.getSwitchList('backup')
            for switch in backupList:
                matchInfo = taskInstance.getBackupMatchInfo(switch)
                datapath = DC._get_datapath(switch)
                newMatch = self._get_new_match(datapath, matchInfo)
                DC.remove_flow(datapath, newMatch)


        DC.sendTaskDeleteReply(taskId)






