'''
\brief Module which coordinate RPL DIO and DAO messages.

\author Xavi Vilajosana <xvilajosana@eecs.berkeley.edu>, January 2013.
\author Thomas Watteyne <watteyne@eecs.berkeley.edu>, April 2013.
'''

import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('RPL')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import threading
import struct
from datetime import datetime

from pydispatch import dispatcher

from eventBus import eventBusClient
import SourceRoute
import openvisualizer_utils as u

class RPL(eventBusClient.eventBusClient):
    
    _TARGET_INFORMATION_TYPE  = 0x05
    _TRANSIT_INFORMATION_TYPE = 0x06
    
    # Period between successive DIOs, in seconds.
    DIO_PERIOD                    = 10                          
    
    # http://www.iana.org/assignments/protocol-numbers/protocol-numbers.xml 
    IANA_ICMPv6_RPL_TYPE          = 155              
    
    # RPL DIO (RFC6550)
    DIO_OPT_GROUNDED              = 1<<7
    MOP_DIO_A                     = 1<<5
    MOP_DIO_B                     = 1<<4
    MOP_DIO_C                     = 1<<3
    PRF_DIO_A                     = 1<<2
    PRF_DIO_B                     = 1<<1
    PRF_DIO_C                     = 1<<0
    
    def __init__(self):
        
        # log
        log.debug("create instance")
        
        # store params
        
        # initialize parent class
        eventBusClient.eventBusClient.__init__(
            self,
            name                  = 'RPL',
            registrations         =  [
                {
                    'sender'      : self.WILDCARD,
                    'signal'      : 'networkPrefix',
                    'callback'    : self._networkPrefix_notif,
                },
                {
                    'sender'      : self.WILDCARD,
                    'signal'      : 'infoDagRoot',
                    'callback'    : self._infoDagRoot_notif,
                },
                {
                    'sender'      : self.WILDCARD,
                    'signal'      : 'getSourceRoute',
                    'callback'    : self._getSourceRoute_notif,
                },
            ]
        )
        
        # local variables
        self.stateLock            = threading.Lock()
        self.state                = {}
        self.networkPrefix        = None
        self.dagRootEui64         = None
        self.sourceRoute          = SourceRoute.SourceRoute()
        self.latencyStats         = {}
        
        # send a DIO periodically
        self._scheduleSendDIO(self.DIO_PERIOD) 
    
    #======================== public ==========================================
    
    #======================== private =========================================
    
    #==== handle EventBus notifications
    
    def _networkPrefix_notif(self,sender,signal,data):
        '''
        \brief Record the network prefix.
        '''
        # store
        with self.stateLock:
            self.networkPrefix    = data[:]
    
    def _infoDagRoot_notif(self,sender,signal,data):
        '''
        \brief Record the DAGroot's EUI64 address.
        '''
        # store
        with self.stateLock:
            self.dagRootEui64     = data['eui64'][:]
        
        # register to RPL traffic
        if self.networkPrefix and self.dagRootEui64:
            self.register(
                sender            = self.WILDCARD,
                signal            = (
                    tuple(self.networkPrefix + self.dagRootEui64),
                    self.PROTO_ICMPv6,
                    self.IANA_ICMPv6_RPL_TYPE
                ),
                callback          = self._fromMoteDataLocal_notif,
            )
    
    def _fromMoteDataLocal_notif(self,sender,signal,data):
        '''
        \brief Called when receiving fromMote.data.local, probably a DAO.
        '''      
        # indicate data to topology
        self._indicateDAO(data)
        return True
    
    def _getSourceRoute_notif(self,sender,signal,data):
        destination = data
        return self.sourceRoute.getSourceRoute(destination)
    
    #===== send DIO
    
    def _scheduleSendDIO(self,interval):
        '''
        \brief Schedule to send a DIO sometime in the future.
        
        \param[in] interval In how many seconds the DIO is scheduled to be
            sent.
        '''
        self.timer = threading.Timer(interval,self._sendDIO)
        self.timer.start()
    
    def _sendDIO(self):
        '''
        \brief Send a DIO.
        '''
        # don't send DIO if I didn't discover the DAGroot EUI64.
        if not self.dagRootEui64:
            
            # reschule to try again later
            self._scheduleSendDIO(self.DIO_PERIOD)
            
            # stop here
            return
        
        # the list of bytes to be sent to the DAGroot.
        # - [8B]       destination MAC address
        # - [variable] IPHC+ header
        dio                  = []
        
        # next hop: broadcast address
        nextHop              = [0xff]*8
        
        # IPHC header
        dio                 += [0x78]        # dispatch byte
        dio                 += [0x33]        # dam sam
        dio                 += [0x3A]        # next header (0x3A=ICMPv6)
        dio                 += [0x00]        # HLIM
        
        # ICMPv6 header
        idxICMPv6            = len(dio)      # remember where ICMPv6 starts
        dio                 += [155]         # ICMPv6 type (155=RPL)
        dio                 += [0x01]        # ICMPv6 CODE (for RPL 0x01=DIO)
        idxICMPv6CS          = len(dio)      # remember where ICMPv6 checksum starts
        dio                 += [0x00,0x00]   # placeholder for checksum (filled out later)
        
        # DIO header
        dio                 += [0x00]        # instance ID
        dio                 += [0x00]        # version number
        dio                 += [0x00,0x00]   # rank
        dio                 += [
                                  self.DIO_OPT_GROUNDED |
                                  self.MOP_DIO_A        |
                                  self.MOP_DIO_B        |
                                  self.MOP_DIO_C
                               ]             # options: G | 0 | MOP | Prf
        dio                 += [0x00]        # DTSN
        dio                 += [0x00]        # flags
        dio                 += [0x00]        # reserved
        
        # DODAGID
        with self.stateLock:
            dio             += self.networkPrefix
            dio             += self.dagRootEui64
        
        # calculate ICMPv6 checksum over ICMPv6header+ (RFC4443)
        checksum             = u.calculateCRC(dio[idxICMPv6:])
                               
        dio[idxICMPv6CS  ]   = checksum[0]
        dio[idxICMPv6CS+1]   = checksum[1]
        
        # log
        log.debug('sending DIO {0}'.format(u.formatBuf(dio)))
        
        # dispatch
        self.dispatch(
            signal          = 'bytesToMesh',
            data            = (nextHop,dio)
        )
        
        # schedule the next DIO transmission
        self._scheduleSendDIO(self.DIO_PERIOD)


    def _indicateDAO(self,tup):    
        '''
        \brief Indicate a new DAO was received.
        
        This function parses the received packet, and if valid, updates the
        information needed to compute source routes.
        '''
        
        # retrieve source and destination
        try:
            source                = tup[0]
            if len(source)>8: 
                source=source[len(source)-8:]
            #print source    
            dao                   = tup[1]
        except IndexError:
            log.warning("DAO too short ({0} bytes), no space for destination and source".format(len(dao)))
            return
        
        # log
        output                    = []
        output                   += ['received DAO:']
        output                   += ['- source :      {0}'.format(tu.formatAddress(source))]
        output                   += ['- dao :         {0}'.format(tu.formatBuf(dao))]
        output                    = '\n'.join(output)
        log.debug(output)
        
        # retrieve DAO header
        dao_header                = {}
        dao_transit_information   = {}
        dao_target_information    = {}
        
        try:
            # RPL header
            dao_header['RPL_InstanceID']    = dao[0]
            dao_header['RPL_flags']         = dao[1]
            dao_header['RPL_Reserved']      = dao[2]
            dao_header['RPL_DAO_Sequence']  = dao[3]
            # DODAGID
            dao_header['DODAGID']           = dao[4:20]
           
            dao                             = dao[20:]
            # retrieve transit information header and parents
            parents                         = []
            children                        = []
                          
            while (len(dao)>0):  
                if   dao[0]==self._TRANSIT_INFORMATION_TYPE: 
                    # transit information option
                    dao_transit_information['Transit_information_type']             = dao[0]
                    dao_transit_information['Transit_information_length']           = dao[1]
                    dao_transit_information['Transit_information_flags']            = dao[2]
                    dao_transit_information['Transit_information_path_control']     = dao[3]
                    dao_transit_information['Transit_information_path_sequence']    = dao[4]
                    dao_transit_information['Transit_information_path_lifetime']    = dao[5]
                    # address of the parent
                    parents      += [dao[6:14]]
                    dao           = dao[14:]
                elif dao[0]==self._TARGET_INFORMATION_TYPE:
                    dao_target_information['Target_information_type']               = dao[0]
                    dao_target_information['Target_information_length']             = dao[1]
                    dao_target_information['Target_information_flags']              = dao[2]
                    dao_target_information['Target_information_prefix_length']      = dao[3]
                    # address of the child
                    children     += [dao[4:12]]
                    dao           = dao[12:]
                else:
                    log.warning("DAO with wrong Option {0}. Neither Transit nor Target.".format(dao[0]))
                    return
        except IndexError:
            log.warning("DAO too short ({0} bytes), no space for DAO header".format(len(dao)))
            return
        
        # log
        output               = []
        output              += ['parents:']
        for p in parents:
            output          += ['- {0}'.format(tu.formatAddress(p))]
        output              += ['children:']
        for p in children:
            output          += ['- {0}'.format(tu.formatAddress(p))]
        output               = '\n'.join(output)
        log.debug(output)
        print output
        
        # if you get here, the DAO was parsed correctly
        
        # update parents information with parents collected -- calls topology module.
        self.dispatch(          
            signal          = 'updateParents',
            data            =  (tuple(source),parents)  
        )
        
        #with self.dataLock:
        #    self.parents.update({tuple(source):parents})
   