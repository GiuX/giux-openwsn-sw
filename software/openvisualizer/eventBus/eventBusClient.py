import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('eventBusClient')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import threading
import Queue

from pydispatch import dispatcher

class eventBusClient(object):
    
    WILDCARD  = '*'
    
    PROTO_ICMPv6 = 'icmpv6'
    PROTO_UDP = 'udp'
    PROTO_ALL = [
        PROTO_ICMPv6,
        PROTO_UDP
    ]
    
    def __init__(self,name,registrations):
        
        assert type(name)==str
        assert type(registrations)==list
        for r in registrations:
            assert type(r)==dict
            for k in r.keys():
                assert k in ['signal','sender','callback']
        
        # log
        log.debug("create instance")
        
        # store params
        self.dataLock        = threading.RLock()
        self.registrations   = []
        
        # give this thread a name
        self.name            = name
        
        # local variables
        self.goOn            = True
        
        # register registrations
        for r in registrations:
            self.register(
                sender       = r['sender'],
                signal       = r['signal'],
                callback     = r['callback'],
            )
        
        # connect to dispatcher
        dispatcher.connect(
            receiver = self._eventBusNotification,
        )
    
    #======================== public ==========================================
    
    def dispatch(self,signal,data):
        return dispatcher.send(
            sender = self.name,
            signal = signal,
            data   = data,
        )
    
    def register(self,sender,signal,callback):
        
        newRegistration = {
            'sender':        sender,
            'signal':        signal,
            'callback':      callback,
            'numRx':         0,
        }
        with self.dataLock:
            self.registrations += [newRegistration]
    
    def unregister(self,sender,signal,callback):
        with self.dataLock:
            rem = None
            for s in self.registrations:
                if self._signalsEquivalent(s, signal):
                    rem=s
                    break
            if (rem!=None):
                self.registrations.remove(rem) 
    
    #======================== private =========================================
    
    def _eventBusNotification(self,signal,sender,data):
        
        callback = None
        
        # find the callback
        with self.dataLock:
            for r in self.registrations:
                if (
                        self._signalsEquivalent(r['signal'],signal) and
                        (r['sender']==sender or r['sender']==self.WILDCARD)
                    ):
                    callback = r['callback']
        
        if not callback:
            return None
        
        # call the callback
        try:
            return callback(
                sender = sender,
                signal = signal,
                data   = data,
            )
        except TypeError as err:
            output = "ERROR could not call {0}, err={1}".format(callback,err)
            log.critical(output)
            print output
    
    def _signalsEquivalent(self,s1,s2):
        if type(s1)==type(s2)==str:
            if (s1==s2) or (s1==self.WILDCARD) or (s2==self.WILDCARD):
                return True
            else:
                return False
        elif type(s1)==type(s2)==tuple:
            assert len(s1)==len(s2)==3
            for i in range(3):
                if (s1[i]==s2[i]) or (s1[i]==self.WILDCARD) or (s2[i]==self.WILDCARD):
                    return True
                else:
                    return False
        return False
    
    
    def _dispatchProtocol(self,signal,data):
        ''' used to sent to the eventBus a signal and look whether someone responds or not'''
        temp = self.dispatch(
              signal       = signal,
              data         = data,
        )
        for (function,returnVal) in temp:
            if returnVal!=None:
                log.debug("returning true is subscribed to signal {0}, {1}".format(signal,returnVal))    
                return True
        
        log.debug("returning false as nobody is subscribed to signal {0}, {1}".format(signal,temp))    
        return False
    
    def _dispatchAndGetResult(self,signal,data):
        temp = self.dispatch(
            signal       = signal, 
            data         = data,
        )
        for (function,returnVal) in temp:
            if returnVal!=None:
                return returnVal
        raise SystemError('No answer to signal _dispatchAndGetResult')
    