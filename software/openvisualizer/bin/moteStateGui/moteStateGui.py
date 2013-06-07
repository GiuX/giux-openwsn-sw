import sys
import os
if __name__=='__main__':
    here = sys.path[0]
    sys.path.insert(0, os.path.join(here, '..', '..','eventBus','PyDispatcher-2.0.3'))# PyDispatcher-2.0.3/
    sys.path.insert(0, os.path.join(here, '..', '..'))                                # openvisualizer/
    sys.path.insert(0, os.path.join(here, '..', '..', '..', 'openUI'))                # openUI/
    sys.path.insert(0, os.path.join(here, '..', '..', '..'))                          # software/
    sys.path.insert(0, os.path.join(here, '..', '..', '..', '..', '..', 'openwsn-fw', 'firmware','openos','projects','common'))

import logging
import logging.config

from optparse import OptionParser

from eventBus      import eventBusMonitor
from moteProbe     import moteProbe
from moteConnector import moteConnector
from moteState     import moteState
from RPL           import RPL
from openLbr       import openLbr
from openTun       import openTun
from RPL           import UDPLatency
from RPL           import topology
import OpenWindow
import OpenFrameState
import OpenFrameButton
import OpenFrameLbr
import OpenFrameEventBus
from SimEngine import SimEngine, \
                      MoteHandler
from openCli   import SimCli

import Tkinter

class MenuUpdateFrame(Tkinter.Frame):
    
    def setMoteStateHandler(self,ms):
        self.ms              = ms
    
    def setMenuList(self,menuList):
        self.menuList        = menuList
    
    def updateMenuLabel(self,indexToUpdate):
        rawLabel  = self.ms.getStateElem(moteState.moteState.ST_IDMANAGER).get16bAddr()
        if rawLabel:
            menuLabel = ''.join(['%02x'%b for b in rawLabel])
            self.menuList.entryconfig(
                indexToUpdate,
                label=menuLabel,
            )

class MoteStateGui(object):
    
    GUI_UPDATE_PERIOD      = 500
    MENUENTRY_STATE        = 'motes'
    MENUENTRY_LBR          = 'lbr'
    MENUENTRY_EVENTBUS     = 'eventBus'
    
    def __init__(self,eventBusMonitor,
                      moteProbes,
                      moteConnectors,
                      moteStates,
                      openLbr):
        
        # store params
        self.eventBusMonitor        = eventBusMonitor
        self.moteProbes             = moteProbes
        self.moteConnectors         = moteConnectors
        self.moteStates             = moteStates
        self.openLbr                = openLbr
        self.menuFrames             = []
        
        # local variables
        self.window                 = OpenWindow.OpenWindow("mote state GUI")
        
        #===== mote states frame
        menuNames                   = []
        self.menuFrames             = []
        for ms in self.moteStates:
            thisFrame               = MenuUpdateFrame(self.window)
            thisFrame.setMoteStateHandler(ms)
            frameOrganization = [
                [
                    moteState.moteState.ST_ISSYNC,
                    moteState.moteState.ST_ASN,
                    moteState.moteState.ST_MYDAGRANK,
                    moteState.moteState.ST_OUPUTBUFFER,
                    moteState.moteState.ST_BACKOFF,
                ],
                [
                    moteState.moteState.TRIGGER_DAGROOT,
                    moteState.moteState.ST_IDMANAGER,
                ],
                [
                    moteState.moteState.ST_MACSTATS,
                ],
                [
                    moteState.moteState.ST_SCHEDULE,
                    moteState.moteState.ST_QUEUE,
                ],
                [
                    moteState.moteState.ST_NEIGHBORS,
                ],
                [
                    moteState.moteState.ST_NETLATENCY, #MY
                ],
            ]
            for row in range(len(frameOrganization)):
                tempRowFrame = Tkinter.Frame(thisFrame)
                tempRowFrame.grid(row=row)
                for column in range(len(frameOrganization[row])):
                    stateOrTrigger = frameOrganization[row][column]
                    if   stateOrTrigger in moteState.moteState.ST_ALL:
                        tempFrameState = OpenFrameState.OpenFrameState(
                            guiParent       = tempRowFrame,
                            frameName       = stateOrTrigger,
                            row             = 0,
                            column          = column,
                        )
                        tempFrameState.startAutoUpdate(
                            updatePeriod    = self.GUI_UPDATE_PERIOD,
                            updateFunc      = ms.getStateElem,
                            updateParams    = (stateOrTrigger,),
                        )
                        tempFrameState.show()
                    elif stateOrTrigger in moteState.moteState.TRIGGER_ALL:
                        tempFrameButton = OpenFrameButton.OpenFrameButton(
                            callfunction    = ms.triggerAction,
                            callparams      = (stateOrTrigger,),
                            guiParent       = tempRowFrame,
                            frameName       = stateOrTrigger,
                            buttonText      = 'toggle',
                            row             = 0,
                            column          = column,
                        )
                        tempFrameButton.show()
                    else:
                        raise SystemError('unexpected stateOrTrigger={0}'.format(stateOrTrigger))
            
            menuNames       += ['{0}'.format(ms.moteConnector.serialport)]
            self.menuFrames += [thisFrame]
        
        # add to menu
        menuList = self.window.addMenuList(
            listname =  self.MENUENTRY_STATE,
            names =     menuNames,
            frames =    self.menuFrames,
        )
        
        for menuFrame in self.menuFrames:
            menuFrame.setMenuList(menuList)
        
        menuList.config(
            postcommand=self._updateMenuFrameNames
        )
        
        #===== openLbr Frame
        # TODO
        
        #===== eventBusMonitor Frame
        
        thisFrame            = Tkinter.Frame(self.window)
        
        tempFrameEventBus    = OpenFrameEventBus.OpenFrameEventBus(
            thisFrame,
            self.eventBusMonitor,
            row=1
        )
        tempFrameEventBus.show()
        
        # add to menu
        self.window.addMenuItem(
            name =      self.MENUENTRY_EVENTBUS,
            frame =     thisFrame,
        )
        
    #======================== public ==========================================
    
    def start(self):
        self.window.startGui()
    
    #======================== private =========================================
    
    def _updateMenuFrameNames(self):
        for i in range(len(self.menuFrames)):
            self.menuFrames[i].updateMenuLabel(i)
    
class MoteStateGui_app(object):
    
    def __init__(self,simulatorMode,numMotes):
        
        # store params
        self.simulatorMode        = simulatorMode
        self.numMotes             = numMotes
        
        # local variables
        self.eventBusMonitor      = eventBusMonitor.eventBusMonitor()
        self.openLbr              = openLbr.OpenLbr()
        self.rpl                  = RPL.RPL()
        self.topology             = topology.topology()
        self.udpLatency           = UDPLatency.UDPLatency()
        self.openTun              = openTun.OpenTun() # call last since indicates prefix
        if self.simulatorMode:
            self.simengine        = SimEngine.SimEngine()
            self.simengine.start()
        
        # create a moteProbe for each mote
        if not self.simulatorMode:
            # in "hardware" mode, motes are connected to the serial port
            
            self.moteProbes       = [
                moteProbe.moteProbe(serialport=sp) for sp in moteProbe.findSerialPorts()
            ]
        else:
            # in "simulator" mode, motes are emulated
            
            import oos_openwsn
            self.moteProbes       = []
            for _ in range(self.numMotes):
                moteHandler       = MoteHandler.MoteHandler(self.simengine,oos_openwsn.OpenMote())
                self.simengine.indicateNewMote(moteHandler)
                self.moteProbes  += [moteProbe.moteProbe(emulatedMote=moteHandler)]
        
        # create a moteConnector for each moteProbe
        self.moteConnectors       = [
            moteConnector.moteConnector(mp.getSerialPortName()) for mp in self.moteProbes
        ]
        
        # create a moteState for each moteConnector
        self.moteStates           = [
            moteState.moteState(mc) for mc in self.moteConnectors
        ]
        
        # create an open GUI
        gui = MoteStateGui(
            self.eventBusMonitor,
            self.moteProbes,
            self.moteConnectors,
            self.moteStates,
            self.openLbr,
        )
        
        # boot all emulated motes, if applicable
        if self.simulatorMode:
            self.simengine.pause()
            now = self.simengine.timeline.getCurrentTime()
            for rank in range(self.simengine.getNumMotes()):
                moteHandler = self.simengine.getMoteHandler(rank)
                self.simengine.timeline.scheduleEvent(
                    now,
                    moteHandler.getId(),
                    moteHandler.hwSupply.switchOn,
                    moteHandler.hwSupply.INTR_SWITCHON
                )
            self.simengine.resume()
        
        # start the GUI
        gui.start()
    
    #======================== GUI callbacks ===================================

#============================ main ============================================

def parseCliOptions():
    
    parser = OptionParser()
    
    parser.add_option( '--sim', '-s',
        dest       = 'simulatorMode',
        default    = False,
        action     = 'store_true',
    )
    
    parser.add_option( '-n',
        dest       = 'numMotes',
        default    = 3,
    )
    
    (opts, args)  = parser.parse_args()
    
    return opts

def main(simulatorMode,numMotes):
    appDir = '.'
    logging.config.fileConfig(os.path.join(appDir,'logging.conf'), {'logDir': appDir})
    app = MoteStateGui_app(simulatorMode,numMotes)

if __name__=="__main__":
    
    opts = parseCliOptions()
    args = opts.__dict__
    
    main(
        simulatorMode   = args['simulatorMode'],
        numMotes        = args['numMotes'],
    )