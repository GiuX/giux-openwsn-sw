import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('moteProbe')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

import os
if os.name=='nt':       # Windows
   import _winreg as winreg
elif os.name=='posix':  # Linux
   import glob
import threading

import serial
import time
import sys

from   pydispatch import dispatcher
import OpenHdlc
import openvisualizer_utils as u
from   moteConnector import OpenParser

#============================ functions =======================================

BAUDRATE_TELOSB = 115200 # poipoipoi
BAUDRATE_GINA   = 115200

def findSerialPorts():
    '''
    \brief Returns the serial ports of the motes connected to the computer.
    
    \returns A list of tuples (name,baudrate) where:
        - name is a strings representing a serial port, e.g. 'COM1'
        - baudrate is an int representing the baurate, e.g. 115200
    '''
    serialports = []
    
    if os.name=='nt':
        path = 'HARDWARE\\DEVICEMAP\\SERIALCOMM'
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        for i in range(winreg.QueryInfoKey(key)[1]):
            try:
                val = winreg.EnumValue(key,i)
            except:
                pass
            else:
                if   val[0].find('VCP')>-1:
                    serialports.append( (str(val[1]),BAUDRATE_TELOSB) )
                elif val[0].find('Silabser')>-1:
                    serialports.append( (str(val[1]),BAUDRATE_GINA) )
    elif os.name=='posix':
        serialports = [(s,BAUDRATE_GINA) for s in glob.glob('/dev/ttyUSB*')]
    
    # log
    log.debug("discovered following COM port: {0}".format(['{0}@{1}'.format(s[0],s[1]) for s in serialports]))
    
    return serialports

#============================ class ===========================================

class moteProbe(threading.Thread):
    
    def __init__(self,serialport):
        
        # store params
        self.serialportName       = serialport[0]
        self.serialportBaudrate   = serialport[1]
        
        # log
        log.info("creating moteProbe attaching to {0}@{1}".format(
                self.serialportName,
                self.serialportBaudrate,
            )
        )
        
        # local variables
        self.hdlc                 = OpenHdlc.OpenHdlc()
        self.lastRxByte           = self.hdlc.HDLC_FLAG
        self.busyReceiving        = False
        self.inputBuf             = ''
        self.outputBuf            = []
        self.outputBufLock        = threading.RLock()
        self.dataLock             = threading.Lock()
        
        # initialize the parent class
        threading.Thread.__init__(self)
        
        # give this thread a name
        self.name                 = 'moteProbe@'+self.serialportName
       
        # connect to dispatcher
        dispatcher.connect(
            self._bufferDataToSend,
            signal = 'fromMoteConnector@'+self.serialportName,
        )
        
        # start myself
        self.start()
    
    #======================== thread ==========================================
    
    def run(self):
        try:
            # log
            log.debug("start running")
        
            while True:     # open serial port
                log.debug("open serial port {0}@{1}".format(self.serialportName,self.serialportBaudrate))
                self.serial = serial.Serial(self.serialportName,self.serialportBaudrate)
                while True: # read bytes from serial port
                    try:
                        rxByte = self.serial.read(1)
                    except Exception as err:
                        log.warning(err)
                        time.sleep(1)
                        break
                    else:
                        if      (
                                    (not self.busyReceiving)             and 
                                    self.lastRxByte==self.hdlc.HDLC_FLAG and
                                    rxByte!=self.hdlc.HDLC_FLAG
                                ):
                            # start of frame
                            log.debug("{0}: start of hdlc frame {1} {2}".format(self.name, u.formatStringBuf(self.hdlc.HDLC_FLAG), u.formatStringBuf(rxByte)))
                            self.busyReceiving       = True
                            self.inputBuf            = self.hdlc.HDLC_FLAG
                            self.inputBuf           += rxByte
                        elif    (
                                    self.busyReceiving                   and
                                    rxByte!=self.hdlc.HDLC_FLAG
                                ):
                            # middle of frame
                            
                            self.inputBuf           += rxByte
                        elif    (
                                    self.busyReceiving                   and
                                    rxByte==self.hdlc.HDLC_FLAG
                                ):
                            # end of frame
                            log.debug("{0}: end of hdlc frame {1} ".format(self.name, u.formatStringBuf(rxByte)))
                            self.busyReceiving       = False
                            self.inputBuf           += rxByte
                            
                            try:
                                tempBuf = self.inputBuf
                                self.inputBuf        = self.hdlc.dehdlcify(self.inputBuf)
                                log.debug("{0}: {2} dehdlcized input: {1}".format(self.name, u.formatStringBuf(self.inputBuf), u.formatStringBuf(tempBuf)))
                            except OpenHdlc.HdlcException as err:
                                log.warning('{0}: invalid serial frame: {2} {1}'.format(self.name, err, u.formatStringBuf(tempBuf)))
                            else:
                                if self.inputBuf==chr(OpenParser.OpenParser.SERFRAME_MOTE2PC_REQUEST):
                                      with self.outputBufLock:
                                        if self.outputBuf:
                                            outputToWrite = self.outputBuf.pop(0)
                                            self.serial.write(outputToWrite)
                                else:
                                    # dispatch
                                    dispatcher.send(
                                        sender        = self.name,
                                        signal        = 'fromProbeSerial@'+self.serialportName,
                                        data          = self.inputBuf[:],
                                    )
                        
                        self.lastRxByte = rxByte
        except Exception as err:
            errMsg=u.formatCrashMessage(self.name,err)
            print errMsg
            log.critical(errMsg)
            sys.exit(-1)
    
    #======================== public ==========================================
    
    def getSerialPortName(self):
        with self.dataLock:
            return self.serialportName
    
    def getSerialPortBaudrate(self):
        with self.dataLock:
            return self.serialportBaudrate
    
    def quit(self):
        raise NotImplementedError()
    
    #======================== private =========================================
    
    def _bufferDataToSend(self,data):
        
        # frame with HDLC
        hdlcData = self.hdlc.hdlcify(data)
        
        # add to outputBuf
        with self.outputBufLock:
            self.outputBuf += [hdlcData]
