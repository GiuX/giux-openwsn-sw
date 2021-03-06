import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('moteState')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import copy
import time
import threading
import json

from moteConnector import ParserStatus
from eventBus      import eventBusClient
from openType      import openType,         \
                          typeAsn,          \
                          typeAddr,         \
                          typeCellType,     \
                          typeComponent,    \
                          typeRssi

class OpenEncoder(json.JSONEncoder):
    def default(self, obj):
        if   isinstance(obj, (StateElem,openType.openType)):
            return { obj.__class__.__name__: obj.__dict__ }
        else:
            return super(OpenEncoder, self).default(obj)
                          
class StateElem(object):
    
    def __init__(self):
        self.meta                      = [{}]
        self.data                      = []
        
        self.meta[0]['numUpdates']     = 0
        self.meta[0]['lastUpdated']    = None
    
    #======================== public ==========================================
    
    def update(self):
        self.meta[0]['lastUpdated']    = time.time()
        self.meta[0]['numUpdates']    += 1
    
    def toJson(self):
        return json.dumps(self._toDict(),sort_keys=True,indent=4)
    
    def __str__(self):
        return self.toJson()
    
    #======================== private =========================================
    
    def _toDict(self):
        returnVal = {}
        returnVal['meta'] = self._elemToDict(self.meta)
        returnVal['data'] = self._elemToDict(self.data)
        return returnVal
    
    def _elemToDict(self,elem):
        returnval = []
        for rowNum in range(len(elem)):
            if   isinstance(elem[rowNum],dict):
                returnval.append({})
                for k,v in elem[rowNum].items():
                    if isinstance(v,(list, tuple)):
                        returnval[-1][k]    = [m._toDict() for m in v]
                    else:
                        if   isinstance(v,openType.openType):
                           returnval[-1][k] = str(v)
                        elif isinstance(v,type):
                           returnval[-1][k] = v.__name__
                        else:
                           returnval[-1][k] = v
            elif isinstance(elem[rowNum],StateElem):
                parsedRow = elem[rowNum]._toDict()
                assert('data' in parsedRow)
                assert(len(parsedRow['data'])<2)
                if len(parsedRow['data'])==1:
                    returnval.append(parsedRow['data'][0])
            else:
                raise SystemError("can not parse elem of type {0}".format(type(elem[rowNum])))
        return returnval

class StateOutputBuffer(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['index_write']         = notif.index_write
        self.data[0]['index_read']          = notif.index_read

class StateAsn(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        if 'asn' not in self.data[0]:
            self.data[0]['asn']             = typeAsn.typeAsn()
        self.data[0]['asn'].update(notif.asn_0_1,
                                   notif.asn_2_3,
                                   notif.asn_4)

class StateAsnSynch(StateElem):                                       # my
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        if 'asnsynch' not in self.data[0]:
            self.data[0]['asnsynch']        = typeAsn.typeAsn()
        self.data[0]['asnsynch'].update(notif.asnSynch_0_1,
                                        notif.asnSynch_2_3,
                                        notif.asnSynch_4)

class StateMacStats(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['numSyncPkt']          = notif.numSyncPkt
        self.data[0]['numSyncAck']          = notif.numSyncAck
        self.data[0]['minCorrection']       = notif.minCorrection
        self.data[0]['maxCorrection']       = notif.maxCorrection
        self.data[0]['numDeSync']           = notif.numDeSync
        self.data[0]['dutyCycle']           = notif.dutyCycle

class StateScheduleRow(StateElem):

    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['slotOffset']          = notif.slotOffset
        if 'type' not in self.data[0]:
            self.data[0]['type']            = typeCellType.typeCellType()
        self.data[0]['type'].update(notif.type)
        self.data[0]['shared']              = notif.shared
        self.data[0]['channelOffset']       = notif.channelOffset
        if 'neighbor' not in self.data[0]:
            self.data[0]['neighbor']        = typeAddr.typeAddr()
        self.data[0]['neighbor'].update(notif.neighbor_type,
                                        notif.neighbor_bodyH,
                                        notif.neighbor_bodyL)
        self.data[0]['numRx']               = notif.numRx
        self.data[0]['numTx']               = notif.numTx
        self.data[0]['numTxACK']            = notif.numTxACK
        if 'lastUsedAsn' not in self.data[0]:
            self.data[0]['lastUsedAsn']     = typeAsn.typeAsn()
        self.data[0]['lastUsedAsn'].update(notif.lastUsedAsn_0_1,
                                           notif.lastUsedAsn_2_3,
                                           notif.lastUsedAsn_4)

class StateBackoff(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['backoffExponent']     = notif.backoffExponent
        self.data[0]['backoff']             = notif.backoff

class StateQueueRow(StateElem):
    
    def update(self,creator,owner):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        
        if 'creator' not in self.data[0]:
            self.data[0]['creator']         = typeComponent.typeComponent()
        self.data[0]['creator'].update(creator)
        if 'owner' not in self.data[0]:
            self.data[0]['owner']           = typeComponent.typeComponent()
        self.data[0]['owner'].update(owner)

class StateQueue(StateElem):
    
    def __init__(self):
        StateElem.__init__(self)
        
        for i in range(10):
            self.data.append(StateQueueRow())
    
    def update(self,notif):
        StateElem.update(self)
        self.data[0].update(notif.creator_0,notif.owner_0)
        self.data[1].update(notif.creator_1,notif.owner_1)
        self.data[2].update(notif.creator_2,notif.owner_2)
        self.data[3].update(notif.creator_3,notif.owner_3)
        self.data[4].update(notif.creator_4,notif.owner_4)
        self.data[5].update(notif.creator_5,notif.owner_5)
        self.data[6].update(notif.creator_6,notif.owner_6)
        self.data[7].update(notif.creator_7,notif.owner_7)
        self.data[8].update(notif.creator_8,notif.owner_8)
        self.data[9].update(notif.creator_9,notif.owner_9)

class StateNeighborsRow(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['used']                     = notif.used
        self.data[0]['parentPreference']         = notif.parentPreference
        self.data[0]['stableNeighbor']           = notif.stableNeighbor
        self.data[0]['switchStabilityCounter']   = notif.switchStabilityCounter
        if 'addr' not in self.data[0]:
            self.data[0]['addr']                 = typeAddr.typeAddr()
        self.data[0]['addr'].update(notif.addr_type,
                                    notif.addr_bodyH,
                                    notif.addr_bodyL)
        self.data[0]['DAGrank']                  = notif.DAGrank
        if 'rssi' not in self.data[0]:
            self.data[0]['rssi']                 = typeRssi.typeRssi()
        self.data[0]['rssi'].update(notif.rssi)
        self.data[0]['numRx']                    = notif.numRx
        self.data[0]['numTx']                    = notif.numTx
        self.data[0]['numTxACK']                 = notif.numTxACK
        self.data[0]['numKA']                    = notif.numKA                       # my
        self.data[0]['numWraps']                 = notif.numWraps
        if 'asn' not in self.data[0]:
            self.data[0]['asn']                  = typeAsn.typeAsn()
        self.data[0]['asn'].update(notif.asn_0_1,
                                   notif.asn_2_3,
                                   notif.asn_4)

class StateIsSync(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['isSync']              = notif.isSync

class StateIdManager(StateElem):
    
    def __init__(self,eventBusClient,moteConnector):
        StateElem.__init__(self)
        self.eventBusClient  = eventBusClient
        self.moteConnector   = moteConnector
    
    def get16bAddr(self):
        try:
            return self.data[0]['my16bID'].addr[:]
        except IndexError:
            return None
    
    def update(self,notif):
    
        # update state
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['isDAGroot']           = notif.isDAGroot
        self.data[0]['isBridge']            = notif.isBridge
        if 'my16bID' not in self.data[0]:
            self.data[0]['my16bID']         = typeAddr.typeAddr()
        self.data[0]['my16bID'].update(notif.my16bID_type,
                                       notif.my16bID_bodyH,
                                       notif.my16bID_bodyL)
        if 'my64bID' not in self.data[0]:
            self.data[0]['my64bID']         = typeAddr.typeAddr()
        self.data[0]['my64bID'].update(notif.my64bID_type,
                                       notif.my64bID_bodyH,
                                       notif.my64bID_bodyL)
        if 'myPANID' not in self.data[0]:
            self.data[0]['myPANID']         = typeAddr.typeAddr()
        self.data[0]['myPANID'].update(notif.myPANID_type,
                                       notif.myPANID_bodyH,
                                       notif.myPANID_bodyL)
        if 'myPrefix' not in self.data[0]:
            self.data[0]['myPrefix']        = typeAddr.typeAddr()
        self.data[0]['myPrefix'].update(notif.myPrefix_type,
                                        notif.myPrefix_bodyH,
                                        notif.myPrefix_bodyL)
        
        # announce information about the DAG root to the eventBus
        if self.data[0]['isDAGroot']==1:
        
            # dispatch
            self.eventBusClient.dispatch(
                signal        = 'infoDagRoot',
                data          = {
                                    'serialPort':   self.moteConnector.serialport,
                                    'eui64':        self.data[0]['my64bID'].addr,
                                },
            )

class StateMyDagRank(StateElem):
    
    def update(self,notif):
        StateElem.update(self)
        if len(self.data)==0:
            self.data.append({})
        self.data[0]['myDAGrank']           = notif.myDAGrank

class StateTable(StateElem):

    def __init__(self,rowClass,columnOrder=None):
        StateElem.__init__(self)
        self.meta[0]['rowClass']            = rowClass
        if columnOrder:
            self.meta[0]['columnOrder']     = columnOrder
        self.data                           = []

    def update(self,notif):
        StateElem.update(self)
        while len(self.data)<notif.row+1:
            self.data.append(self.meta[0]['rowClass']())
        self.data[notif.row].update(notif)

class moteState(eventBusClient.eventBusClient):
    
    ST_OUPUTBUFFER      = 'OutputBuffer'
    ST_ASN              = 'Asn'
    ST_ASNSYNCH         = 'AsnSynch'                       # my
    ST_MACSTATS         = 'MacStats'
    ST_SCHEDULEROW      = 'ScheduleRow'
    ST_SCHEDULE         = 'Schedule'
    ST_BACKOFF          = 'Backoff'
    ST_QUEUEROW         = 'QueueRow'
    ST_QUEUE            = 'Queue'
    ST_NEIGHBORSROW     = 'NeighborsRow'
    ST_NEIGHBORS        = 'Neighbors'
    ST_ISSYNC           = 'IsSync'
    ST_IDMANAGER        = 'IdManager'
    ST_MYDAGRANK        = 'MyDagRank'
    ST_ALL              = [
        ST_OUPUTBUFFER,
        ST_ASN,
        ST_ASNSYNCH,                       # my
        ST_MACSTATS,
        ST_SCHEDULE,
        ST_BACKOFF,
        ST_QUEUE,
        ST_NEIGHBORS,
        ST_ISSYNC,
        ST_IDMANAGER, 
        ST_MYDAGRANK,
    ]
    
    TRIGGER_DAGROOT     = 'DAGroot'
    TRIGGER_ALL         = [
        TRIGGER_DAGROOT,
    ]
    
    def __init__(self,moteConnector):
        
        # log
        log.debug("create instance")
        
        # store params
        self.moteConnector   = moteConnector
        
      
        # local variables
        self.parserStatus                   = ParserStatus.ParserStatus()
        self.stateLock                      = threading.Lock()
        self.state                          = {}
        
        self.state[self.ST_OUPUTBUFFER]     = StateOutputBuffer()
        self.state[self.ST_ASN]             = StateAsn()
        self.state[self.ST_ASNSYNCH]        = StateAsnSynch()
        self.state[self.ST_MACSTATS]        = StateMacStats()
        self.state[self.ST_SCHEDULE]        = StateTable(
                                                StateScheduleRow,
                                                columnOrder = '.'.join(
                                                    [
                                                        'slotOffset',
                                                        'type',
                                                        'shared',
                                                        'channelOffset',
                                                        'neighbor',
                                                        'numRx',
                                                        'numTx',
                                                        'numTxACK',
                                                        'lastUsedAsn',
                                                    ]
                                                )
                                              )
        self.state[self.ST_BACKOFF]         = StateBackoff()
        self.state[self.ST_QUEUE]           = StateQueue()
        self.state[self.ST_NEIGHBORS]       = StateTable(
                                                StateNeighborsRow,
                                                columnOrder = '.'.join(
                                                    [
                                                        'used',
                                                        'parentPreference',
                                                        'stableNeighbor',
                                                        'switchStabilityCounter',
                                                        'addr',
                                                        'DAGrank',
                                                        'rssi',
                                                        'numRx',
                                                        'numTx',
                                                        'numTxACK',
                                                        'numKA',                       # my
                                                        'numWraps',
                                                        'asn',
                                                    ]
                                                ))
        self.state[self.ST_ISSYNC]          = StateIsSync()
        self.state[self.ST_IDMANAGER]       = StateIdManager(
                                                self,
                                                self.moteConnector
                                              )
        self.state[self.ST_MYDAGRANK]       = StateMyDagRank()
        
        self.notifHandlers = {
            self.parserStatus.named_tuple[self.ST_OUPUTBUFFER]:
                self.state[self.ST_OUPUTBUFFER].update,
            self.parserStatus.named_tuple[self.ST_ASN]:
                self.state[self.ST_ASN].update,
            self.parserStatus.named_tuple[self.ST_ASNSYNCH]:                       # my
                self.state[self.ST_ASNSYNCH].update,                               # my
            self.parserStatus.named_tuple[self.ST_MACSTATS]:
                self.state[self.ST_MACSTATS].update,
            self.parserStatus.named_tuple[self.ST_SCHEDULEROW]:
                self.state[self.ST_SCHEDULE].update,
            self.parserStatus.named_tuple[self.ST_BACKOFF]:
                self.state[self.ST_BACKOFF].update,
            self.parserStatus.named_tuple[self.ST_QUEUEROW]:
                self.state[self.ST_QUEUE].update,
            self.parserStatus.named_tuple[self.ST_NEIGHBORSROW]:
                self.state[self.ST_NEIGHBORS].update,
            self.parserStatus.named_tuple[self.ST_ISSYNC]:
                self.state[self.ST_ISSYNC].update,
            self.parserStatus.named_tuple[self.ST_IDMANAGER]:
                self.state[self.ST_IDMANAGER].update,
            self.parserStatus.named_tuple[self.ST_MYDAGRANK]:
                self.state[self.ST_MYDAGRANK].update,
        
        }
              # initialize parent class
        eventBusClient.eventBusClient.__init__(
            self,
            name             = 'moteState@{0}'.format(self.moteConnector.serialport),
            registrations    = [
                {
                    'sender'      : 'moteConnector@{0}'.format(self.moteConnector.serialport),
                    'signal'      : 'fromMote.status',
                    'callback'    : self._receivedStatus_notif,
                },
            ]
        )
    #======================== public ==========================================
    
    def getStateElemNames(self):
        
        self.stateLock.acquire()
        returnVal = self.state.keys()
        self.stateLock.release()
        
        return returnVal
    
    def getStateElem(self,elemName):
        
        if elemName not in self.state:
            raise ValueError('No state called {0}'.format(elemName))
        
        self.stateLock.acquire()
        returnVal = self.state[elemName]
        self.stateLock.release()
        
        return returnVal
    
    def triggerAction(self,action):
        
        # dispatch
        self.dispatch(
            signal        = 'cmdToMote',
            data          = {
                                'serialPort':    self.moteConnector.serialport,
                                'action':        action,
                            },
        )
    
    #======================== private =========================================
    
    def _receivedStatus_notif(self,sender,signal,data):
        
        # log
        log.debug("received {0}".format(data))
        
        # lock the state data
        self.stateLock.acquire()
        
        # call handler
        found = False
        for k,v in self.notifHandlers.items():
            if self._isnamedtupleinstance(data,k):
                found = True
                v(data)
                break
        
        # unlock the state data
        self.stateLock.release()
        
        if found==False:
            raise SystemError("No handler for data {0}".format(data))
    
    def _isnamedtupleinstance(self,var,tupleInstance):
        return var._fields==tupleInstance._fields