'''
\brief Module which receives DAO messages and calculates source routes.

\author Xavi Vilajosana <xvilajosana@eecs.berkeley.edu>, January 2013.
\author Thomas Watteyne <watteyne@eecs.berkeley.edu>, April 2013.
'''

import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('SourceRoute')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import threading

import openvisualizer_utils as u
from eventBus import eventBusClient


class SourceRoute(eventBusClient.eventBusClient):
       
    def __init__(self):
        
        # local variables
        self.dataLock        = threading.Lock()
        self.parents         = {}
        
        # initialize parent class
        eventBusClient.eventBusClient.__init__(
            self,
            name             = 'SourceRoute',
            registrations =  []
        )
    
    #======================== public ==========================================
    
    def getSourceRoute(self,destAddr):
        '''
        \brief Retrieve the source route to a given mote.
        
        \param[in] destAddr The EUI64 address of the final destination.
        
        \return The source route, a list of EUI64 address, ordered from
            destination to source.
        '''
        
        sourceRoute = []
        with self.dataLock:
            try:
                parents=self._dispatchAndGetResult(signal='getParents',data=None)
                self._getSourceRoute_internal(destAddr,sourceRoute,parents)
            except Exception as err:
                log.error(err)
                raise
        
        return sourceRoute
    
    #======================== private =========================================
    
    def _getSourceRoute_internal(self,destAddr,sourceRoute,parents):
        
        if not destAddr:
            # no more parents
            return
        
        if not parents.get(tuple(destAddr)):
            # this node does not have a list of parents
            return
        
        # first time add destination address
        if destAddr not in sourceRoute:
            sourceRoute     += [destAddr]
        
        # pick a parent
        parent               = parents.get(tuple(destAddr))[0]
        
        # avoid loops
        if parent not in sourceRoute:
            sourceRoute     += [parent]
            
            # add non empty parents recursively
            nextparent       = self._getSourceRoute_internal(parent,sourceRoute,parents)
            
            if nextparent:
                sourceRoute += [nextparent]
    
    #======================== helpers =========================================
    