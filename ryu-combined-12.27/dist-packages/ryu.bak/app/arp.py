from ryu.base import app_manager

from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls

from ryu.ofproto import ofproto_v1_3

from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import icmp


class IcmpResponder(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

	def __init__(self,*args,**kwargs):
		super(IcmpResponder,self).__init__(*args,**kwargs)
		self.hw_addr = '20:1a:06:22:fc:65'
		#self.ip_addr = '10.108.90.100'


	@set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
	def _switch_features_handler(self,ev):
		msg=ev.msg
		datapath=msg.datapath
		ofproto=datapath.ofproto
		parser=datapath.ofproto_parser
		actions=[parser.OFPActionOutput(port=ofproto.OFPP_CONTROLLER,
			max_len=ofproto.OFPCML_NO_BUFFER)]

		inst=[parser.OFPInstructionActions(type_=ofproto.OFPIT_APPLY_ACTIONS,
							actions=actions)]
		mod=parser.OFPFlowMod(datapath=datapath,priority=0,
			match=parser.OFPMatch(),instructions=inst)
		datapath.send_msg(mod)

	@set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
	def _packet_in_handler(self,ev):
		msg=ev.msg
		datapath=msg.datapath
		port=msg.match['in_port']
		pkt=packet.Packet(data=msg.data)
        #return a packet object,with an ethernet object in the list of protocol

		self.logger.info("packet-in %s" % (pkt,))
		pkt_ethernet = pkt.get_protocol(ethernet.ethernet)#pkt_ethernet is an ethernet object with dst,src and type
		if not pkt_ethernet:
			return
		pkt_arp=pkt.get_protocol(arp.arp)#pkt_arp is an arp object with ip and mac address
		if pkt_arp:
			self._handle_arp(datapath,port,pkt_ethernet,pkt_arp)
			self.send_arp_event(datapath,port,pkt_arp)#################
			return

		pkt_ipv4=pkt.get_protocol(ipv4.ipv4)
		pkt_icmp=pkt.get_protocol(icmp.icmp)
		if pkt_icmp:
			self._handle_icmp(datapath,port,pkt_ethernet,pkt_ipv4,pkt_icmp)
			return

	def _handle_arp(self,datapath,port,pkt_ethernet,pkt_arp):
		if pkt_arp.opcode !=arp.ARP_REQUEST:
			return
		pkt=packet.Packet()
		pkt.add_protocol(ethernet.ethernet(ethertype=pkt_ethernet.ethertype,
			dst=pkt_ethernet.src,src=self.hw_addr))#src and dst mac addresses
		pkt.add_protocol(arp.arp(opcode=arp.ARP_REPLY,
			src_mac=self.hw_addr,src_ip=pkt_arp.dst_ip,
			dst_mac=pkt_arp.src_mac,dst_ip=pkt_arp.src_ip)
			)

		self._send_packet(datapath,port,pkt)



	def _handle_icmp(self,datapath,port,pkt_ethernet,pkt_ipv4,pkt_icmp):
		if pkt_icmp.type!=icmp.ICMP_ECHO_REQUEST:
			return
		pkt=packet.Packet()
		pkt.add_protocol(ethernet.ethernet(ethertype=pkt_ethernet.ethertype,
			dst=pkt_ethernet.src,
		src=self.hw_addr))
		pkt.add_protocol(ipv4.ipv4(dst=pkt_ipv4.src,src=self.ip_addr,
			proto=pkt_ipv4.proto))
		pkt.add_protocol(icmp.icmp(type_=icmp.ICMP_ECHO_REPLY,
			code=icmp.ICMP_ECHO_CODE,csum=0,datapath=pkt_icmp.data))
		self._send_packet(datapath,port,pkt)


	def _send_packet(self,datapath,port,pkt):
		ofproto=datapath.ofproto
		parser=datapath.ofproto_parser
		pkt.serialize()
		self.logger.info("packet-out %s"% (pkt,))
		data=pkt.data
		actions=[parser.OFPActionOutput(port=port)]
		out=parser.OFPPacketOut(datapath=datapath,buffer_id=ofproto.OFP_NO_BUFFER,
			in_port=ofproto.OFPP_CONTROLLER,actions=actions,data=data)
		datapath.send_msg(out)

############################
	def send_arp_event(self,datapath,port,pkt_arp):		
		ip_to_port = {pkt_arp.src_ip:port}######
		ip_to_mac = {pkt_arp.src_ip:pkt_arp.src_mac}########
		port_to_dpid = {port:datapath}######
		arp_extension_table = {datapath.id:{port:[pkt_arp.src_mac,pkt_arp.src_ip]}}#######
		ev = arpevent(ip_to_port,ip_to_mac,port_to_dpid,arp_extension_table)
		self.send_event('domain_controller',ev)

from ryu.controller import event
class arpevent(event.EventBase)	:
	def __init__(self,ip_to_port,ip_to_mac,port_to_dpid,arp_extension_table):
		super(arpevent,self).__init__()
		self.ip_to_port = ip_to_port
		self.ip_to_mac = ip_to_mac
		self.port_to_dpid = port_to_dpid
		self.arp_extension_table = arp_extension_table
