import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('OpenTun')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import threading
import time

# TODO: import only when Windows

import _winreg as reg
import win32file
import win32event
import pywintypes

from eventBus import eventBusClient

#============================ defines =========================================

## IPv4 configuration of your TUN interface (represented as a list of integers)
TUN_IPv4_ADDRESS    = [ 10,  2,0,1] ##< The IPv4 address of the TUN interface.
TUN_IPv4_NETWORK    = [ 10,  2,0,0] ##< The IPv4 address of the TUN interface's network.
TUN_IPv4_NETMASK    = [255,255,0,0] ##< The IPv4 netmask of the TUN interface.

## Key in the Windows registry where to find all network interfaces (don't change, this is always the same)
ADAPTER_KEY         = r'SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}'

## Value of the ComponentId key in the registry corresponding to your TUN interface.
TUNTAP_COMPONENT_ID = 'tap0901'

def CTL_CODE(device_type, function, method, access):
    return (device_type << 16) | (access << 14) | (function << 2) | method;

def TAP_CONTROL_CODE(request, method):
    return CTL_CODE(34, request, method, 0)

TAP_IOCTL_SET_MEDIA_STATUS        = TAP_CONTROL_CODE( 6, 0)
TAP_IOCTL_CONFIG_TUN              = TAP_CONTROL_CODE(10, 0)

#============================ helper classes ==================================

class TunReadThread(threading.Thread):
    '''
    \brief Thread which continously reads input from a TUN interface.
    
    When data is received from the interface, it calls a callback configured
    during instantiation.
    '''
    
    ETHERNET_MTU        = 1500
    IPv6_HEADER_LENGTH  = 40
    
    def __init__(self,tunIf,callback):
    
        # store params
        self.tunIf                = tunIf
        self.callback             = callback
        
        # local variables
        self.goOn                 = True
        self.overlappedRx         = pywintypes.OVERLAPPED()
        self.overlappedRx.hEvent  = win32event.CreateEvent(None, 0, 0, None)
        
        # initialize parent
        threading.Thread.__init__(self)
        
        # give this thread a name
        self.name                 = 'readThread'
        
        # start myself
        self.start()
    
    def run(self):
        
        rxbuffer = win32file.AllocateReadBuffer(self.ETHERNET_MTU)
        
        while self.goOn:
            
            # wait for data
            l, p = win32file.ReadFile(self.tunIf, rxbuffer, self.overlappedRx)
            win32event.WaitForSingleObject(self.overlappedRx.hEvent, win32event.INFINITE)
            self.overlappedRx.Offset = self.overlappedRx.Offset + len(p)
            
            # convert input from a string to a byte list
            p = [ord(b) for b in p]
            
            # make sure it's an IPv6 packet (starts with 0x6x)
            if (p[0]&0xf0)!=0x60:
               # this is not an IPv6 packet
               continue
            
            # because of the nature of tun for Windows, p contains ETHERNET_MTU
            # bytes. Cut at length of IPv6 packet.
            p = p[:self.IPv6_HEADER_LENGTH+256*p[4]+p[5]]
            
            # call the callback
            self.callback(p)
    
    #======================== public ==========================================
    
    def close(self):
        self.goOn = False
    
    #======================== private =========================================
    
#============================ main class ======================================

class OpenTun(eventBusClient.eventBusClient):
    '''
    \brief Class which interfaces between a TUN virtual interface and an
        EventBus.
    '''
    
    def __init__(self):
        
        # log
        log.debug("create instance")
        
        # store params
        
        # initialize parent class
        eventBusClient.eventBusClient.__init__(
            self,
            name             = 'OpenTun',
            registrations =  [
                {
                    'sender'   : self.WILDCARD,
                    'signal'   : 'v6ToInternet',
                    'callback' : self._v6ToInternet_notif
                }
            ]
        )
        
        # local variables
        self.tunIf           = self._createTunIf()
        self.tunReadThread   = TunReadThread(
            self.tunIf,
            self._v6ToMesh_notif
        )
    
    #======================== public ==========================================
    
    #======================== private =========================================
    
    def _v6ToInternet_notif(self,sender,signal,data):
        '''
        \brief Called when receiving data from the EventBus.
        
        This function forwards the data to the the TUN interface.
        '''
        
        # convert data to string
        data  = ''.join([chr(b) for b in data])
        
        # write over tuntap interface
        win32file.WriteFile(self.tuntap, data, self.overlappedTx)
        win32event.WaitForSingleObject(self.overlappedTx.hEvent, win32event.INFINITE)
        self.overlappedTx.Offset = self.overlappedTx.Offset + len(data)
    
    def _v6ToMesh_notif(self,data):
        '''
        \brief Called when receiving data from the TUN interface.
        
        This function forwards the data to the the EventBus.
        '''
        # dispatch to EventBus
        self.dispatch(
            signal        = 'v6ToMesh',
            data          = data,
        )
    
    def _createTunIf(self):
        '''
        \brief Open a TUN/TAP interface and switch it to TUN mode.
        
        \return The handler of the interface, which can be used for later
            read/write operations.
        '''
        
        # retrieve the ComponentId from the TUN/TAP interface
        componentId = self._get_tuntap_ComponentId()
        
        # create a win32file for manipulating the TUN/TAP interface
        tunIf = win32file.CreateFile(
            r'\\.\Global\%s.tap' % componentId,
            win32file.GENERIC_READ    | win32file.GENERIC_WRITE,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_ATTRIBUTE_SYSTEM | win32file.FILE_FLAG_OVERLAPPED,
            None
        )
        
        # have Windows consider the interface now connected
        win32file.DeviceIoControl(
            tunIf,
            TAP_IOCTL_SET_MEDIA_STATUS,
            '\x01\x00\x00\x00',
            None
        )
        
        # prepare the parameter passed to the TAP_IOCTL_CONFIG_TUN commmand.
        # This needs to be a 12-character long string representing
        # - the tun interface's IPv4 address (4 characters)
        # - the tun interface's IPv4 network address (4 characters)
        # - the tun interface's IPv4 network mask (4 characters)
        configTunParam  = []
        configTunParam += TUN_IPv4_ADDRESS
        configTunParam += TUN_IPv4_NETWORK
        configTunParam += TUN_IPv4_NETMASK
        configTunParam  = ''.join([chr(b) for b in configTunParam])
        
        # switch to TUN mode (by default the interface runs in TAP mode)
        win32file.DeviceIoControl(
            tunIf,
            TAP_IOCTL_CONFIG_TUN,
            configTunParam,
            None
        )
        
        # return the handler of the TUN interface
        return tunIf
    
    #======================== helpers =========================================
    
    def _get_tuntap_ComponentId(self):
        '''
        \brief Retrieve the instance ID of the TUN/TAP interface from the Windows
            registry,
        
        This function loops through all the sub-entries at the following location
        in the Windows registry: reg.HKEY_LOCAL_MACHINE, ADAPTER_KEY
          
        It looks for one which has the 'ComponentId' key set to
        TUNTAP_COMPONENT_ID, and returns the value of the 'NetCfgInstanceId' key.
        
        \return The 'ComponentId' associated with the TUN/TAP interface, a string
            of the form "{A9A413D7-4D1C-47BA-A3A9-92F091828881}".
        '''
        with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, ADAPTER_KEY) as adapters:
            try:
                for i in xrange(10000):
                    key_name = reg.EnumKey(adapters, i)
                    with reg.OpenKey(adapters, key_name) as adapter:
                        try:
                            component_id = reg.QueryValueEx(adapter, 'ComponentId')[0]
                            if component_id == TUNTAP_COMPONENT_ID:
                                return reg.QueryValueEx(adapter, 'NetCfgInstanceId')[0]
                        except WindowsError, err:
                            pass
            except WindowsError, err:
                pass
