#include "openwsn.h"
#include "IEEE802154.h"
#include "packetfunctions.h"
#include "idmanager.h"
#include "openserial.h"

//=========================== variables =======================================

//=========================== prototypes ======================================
void    ieee802154_prependAuxHeader(OpenQueueEntry_t* msg);

//=========================== public ==========================================

void ieee802154_prependHeader(OpenQueueEntry_t* msg,
                              uint8_t           frameType,
                              bool              securityEnabled,
                              uint8_t           sequenceNumber,
                              open_addr_t*      nextHop) {
   uint8_t temp_8b;
   
   
   //Auxilary Security Header 2B
   if (securityEnabled) {
        ieee802154_prependAuxHeader(msg);
   } 
   
   //previousHop address (always 64-bit)
   //packetfunctions_writeAddress(msg,idmanager_getMyID(ADDR_64B),LITTLE_ENDIAN);
   // poipoi: using 16-bit source address
   packetfunctions_writeAddress(msg,idmanager_getMyID(ADDR_16B),LITTLE_ENDIAN);
   //nextHop address
   if (packetfunctions_isBroadcastMulticast(nextHop)) { //broadcast address is always 16-bit
      packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
      *((uint8_t*)(msg->payload)) = 0xFF;
      packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
      *((uint8_t*)(msg->payload)) = 0xFF;
   } else {
      // poipoi: using 16-bit destination address
      packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
      *((uint8_t*)(msg->payload)) = nextHop->addr_64b[6];
      packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
      *((uint8_t*)(msg->payload)) = nextHop->addr_64b[7];
      /*
      switch (nextHop->type) {
         case ADDR_16B:
         case ADDR_64B:
            packetfunctions_writeAddress(msg,nextHop,LITTLE_ENDIAN);
            break;
         default:
            openserial_printError(COMPONENT_IEEE802154,ERR_WRONG_ADDR_TYPE,
                                  (errorparameter_t)nextHop->type,
                                  (errorparameter_t)1);
      }
      */
   }
   //destpan
   packetfunctions_writeAddress(msg,idmanager_getMyID(ADDR_PANID),LITTLE_ENDIAN);
   //dsn
   packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
   *((uint8_t*)(msg->payload)) = sequenceNumber;
   //fcf (2nd byte)
   temp_8b              = 0;
   // poipoi: 16-bit source/dest addresses                                                                                            
                                                                                                //bit8 Seq
                                                                                                //bit9, IE
   temp_8b             |= IEEE154_ADDR_SHORT              << IEEE154_FCF_DEST_ADDR_MODE;        //bit10..11
                                                                                                //bit12..13 Frame version
   temp_8b             |= IEEE154_ADDR_SHORT              << IEEE154_FCF_SRC_ADDR_MODE;         //bit14..15
   /*
   if (packetfunctions_isBroadcastMulticast(nextHop)) {
      temp_8b          |= IEEE154_ADDR_SHORT              << IEEE154_FCF_DEST_ADDR_MODE;
   } else {
      switch (nextHop->type) {
         case ADDR_16B:
            temp_8b    |= IEEE154_ADDR_SHORT              << IEEE154_FCF_DEST_ADDR_MODE;
            break;
         case ADDR_64B:
            temp_8b    |= IEEE154_ADDR_EXT                << IEEE154_FCF_DEST_ADDR_MODE;
            break;
      }
   }
   temp_8b             |= IEEE154_ADDR_EXT                << IEEE154_FCF_SRC_ADDR_MODE;
   */
   packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
   *((uint8_t*)(msg->payload)) = temp_8b;
   //fcf (1st byte)
   temp_8b              = 0;
   temp_8b             |= frameType                       << IEEE154_FCF_FRAME_TYPE;
   temp_8b             |= securityEnabled                 << IEEE154_FCF_SECURITY_ENABLED;
   temp_8b             |= IEEE154_PENDING_NO_FRAMEPENDING << IEEE154_FCF_FRAME_PENDING;
   if (frameType==IEEE154_TYPE_ACK || packetfunctions_isBroadcastMulticast(nextHop)) {
      temp_8b          |= IEEE154_ACK_NO_ACK_REQ          << IEEE154_FCF_ACK_REQ;
   } else {
      temp_8b          |= IEEE154_ACK_YES_ACK_REQ         << IEEE154_FCF_ACK_REQ;
   }
   temp_8b             |= IEEE154_PANID_COMPRESSED        << IEEE154_FCF_INTRAPAN;
   packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
   *((uint8_t*)(msg->payload)) = temp_8b;
}

void ieee802154_retrieveHeader(OpenQueueEntry_t*      msg,
                               ieee802154_header_iht* ieee802514_header) {
   uint8_t temp_8b;
   
   ieee802514_header->valid=FALSE;
   
   ieee802514_header->headerLength = 0;
   //fcf, byte 1
   if (ieee802514_header->headerLength>msg->length) {  return; }
   temp_8b = *((uint8_t*)(msg->payload)+ieee802514_header->headerLength);
   ieee802514_header->frameType         = (temp_8b >> IEEE154_FCF_FRAME_TYPE      ) & 0x07;//3b
   ieee802514_header->securityEnabled   = (temp_8b >> IEEE154_FCF_SECURITY_ENABLED) & 0x01;//1b
   ieee802514_header->framePending      = (temp_8b >> IEEE154_FCF_FRAME_PENDING   ) & 0x01;//1b
   ieee802514_header->ackRequested      = (temp_8b >> IEEE154_FCF_ACK_REQ         ) & 0x01;//1b
   ieee802514_header->panIDCompression  = (temp_8b >> IEEE154_FCF_INTRAPAN        ) & 0x01;//1b
   ieee802514_header->headerLength += 1;
   //fcf, byte 2
   if (ieee802514_header->headerLength>msg->length) {  return; }
   temp_8b = *((uint8_t*)(msg->payload)+ieee802514_header->headerLength);
   switch ( (temp_8b >> IEEE154_FCF_DEST_ADDR_MODE ) & 0x03 ) {
      case IEEE154_ADDR_NONE:
         ieee802514_header->dest.type = ADDR_NONE;
         break;
      case IEEE154_ADDR_SHORT:
         ieee802514_header->dest.type = ADDR_16B;
         break;
      case IEEE154_ADDR_EXT:
         ieee802514_header->dest.type = ADDR_64B;
         break;
      default:
         openserial_printError(COMPONENT_IEEE802154,ERR_IEEE154_UNSUPPORTED,
                               (errorparameter_t)1,
                               (errorparameter_t)(temp_8b >> IEEE154_FCF_DEST_ADDR_MODE ) & 0x03);
         break;
   }
   switch ( (temp_8b >> IEEE154_FCF_SRC_ADDR_MODE ) & 0x03 ) {
      case IEEE154_ADDR_NONE:
         ieee802514_header->src.type = ADDR_NONE;
         break;
      case IEEE154_ADDR_SHORT:
         ieee802514_header->src.type = ADDR_16B;
         break;
      case IEEE154_ADDR_EXT:
         ieee802514_header->src.type = ADDR_64B;
         break;
      default:
         openserial_printError(COMPONENT_IEEE802154,ERR_IEEE154_UNSUPPORTED,
                               (errorparameter_t)2,
                               (errorparameter_t)(temp_8b >> IEEE154_FCF_SRC_ADDR_MODE ) & 0x03);
         break;
   }
   ieee802514_header->headerLength += 1;
   //sequenceNumber
   if (ieee802514_header->headerLength>msg->length) {  return; }
   ieee802514_header->dsn  = *((uint8_t*)(msg->payload)+ieee802514_header->headerLength);
   ieee802514_header->headerLength += 1;
   //panID
   if (ieee802514_header->headerLength>msg->length) {  return; }
   packetfunctions_readAddress(((uint8_t*)(msg->payload)+ieee802514_header->headerLength),
                               ADDR_PANID,
                               &ieee802514_header->panid,
                               LITTLE_ENDIAN);
   ieee802514_header->headerLength += 2;
   //dest
   if (ieee802514_header->headerLength>msg->length) {  return; }
   switch (ieee802514_header->dest.type) {
      case ADDR_NONE:
         break;
      case ADDR_16B:
         packetfunctions_readAddress(((uint8_t*)(msg->payload)+ieee802514_header->headerLength),
                                     ADDR_16B,
                                     &ieee802514_header->dest,
                                     LITTLE_ENDIAN);
         ieee802514_header->headerLength += 2;
         // poipoi: spoofing 64-bit destination address
         if        (idmanager_isMyAddress(&ieee802514_header->dest)==TRUE) {
            memcpy(&ieee802514_header->dest,idmanager_getMyID(ADDR_64B),sizeof(open_addr_t));
         } else if (packetfunctions_isBroadcastMulticast(&ieee802514_header->dest)==FALSE) {
            ieee802514_header->dest.addr_64b[7] = ieee802514_header->dest.addr_64b[1];
            ieee802514_header->dest.addr_64b[6] = ieee802514_header->dest.addr_64b[0];
            ieee802514_header->dest.addr_64b[5] = 0x00;
            ieee802514_header->dest.addr_64b[4] = 0x00;
            ieee802514_header->dest.addr_64b[3] = 0x00;
            ieee802514_header->dest.addr_64b[2] = 0x00;
            ieee802514_header->dest.addr_64b[1] = 0x00;
            ieee802514_header->dest.addr_64b[0] = 0x00;
            ieee802514_header->dest.type        = ADDR_64B;
         }
         
         if (ieee802514_header->headerLength>msg->length) {  return; }
         break;
      case ADDR_64B:
         packetfunctions_readAddress(((uint8_t*)(msg->payload)+ieee802514_header->headerLength),
                                     ADDR_64B,
                                     &ieee802514_header->dest,
                                     LITTLE_ENDIAN);
         ieee802514_header->headerLength += 8;
         if (ieee802514_header->headerLength>msg->length) {  return; }
         break;
   }
   //src
   switch (ieee802514_header->src.type) {
      case ADDR_NONE:
         break;
      case ADDR_16B:
         packetfunctions_readAddress(((uint8_t*)(msg->payload)+ieee802514_header->headerLength),
                                     ADDR_16B,
                                     &ieee802514_header->src,
                                     LITTLE_ENDIAN);
         ieee802514_header->headerLength += 2;
         
         // poipoi: spoofing 64-bit source address
         ieee802514_header->src.addr_64b[7] = ieee802514_header->src.addr_64b[1];
         ieee802514_header->src.addr_64b[6] = ieee802514_header->src.addr_64b[0];
         ieee802514_header->src.addr_64b[5] = 0x00;
         ieee802514_header->src.addr_64b[4] = 0x00;
         ieee802514_header->src.addr_64b[3] = 0x00;
         ieee802514_header->src.addr_64b[2] = 0x00;
         ieee802514_header->src.addr_64b[1] = 0x00;
         ieee802514_header->src.addr_64b[0] = 0x00;
         ieee802514_header->src.type        = ADDR_64B;
         
         if (ieee802514_header->headerLength>msg->length) {  return; }
         break;
      case ADDR_64B:
         packetfunctions_readAddress(((uint8_t*)(msg->payload)+ieee802514_header->headerLength),
                                     ADDR_64B,
                                     &ieee802514_header->src,
                                     LITTLE_ENDIAN);
         ieee802514_header->headerLength += 8;
         if (ieee802514_header->headerLength>msg->length) {  return; }
         break;
   }
   // if you reach this, the header is valid
   ieee802514_header->valid=TRUE;
}

//=========================== private =========================================
void ieee802154_prependAuxHeader(OpenQueueEntry_t* msg) {
    uint8_t      temp_8b;
   
    //2nd byte, Key identifier 
   packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
   *((uint8_t*)(msg->payload)) = INTIAL_KEY_ID;                         //INITIAL_KEY_ID =0x07
   
   //1st byte, security control
   temp_8b       = 0;
   temp_8b      |= IEEE154_SECURITY_LEVEL_32MIC              << IEEE154_AUX_SECURITY_LEVEL;            //b0..2 secuity level =01-32bitMIC   
   temp_8b      |= IEEE154_KEY_FROM_INDEX                    << IEEE154_AUX_KEY_ID_MODE;               //b3-b4 key identifier mode =01- key is determined from 1B key index
   temp_8b      |= IEEE154_COUNTER_SUPPRESSION_YES           << IEEE154_AUX_FRAME_COUNTER_SUPPRESSION; //b5 frame counter suppression, =1-no frame counter is sent
   temp_8b      |= IEEE154_COUNTER_SIZE_5B                   << IEEE154_AUX_FRAME_COUNTER_SIZE;        //b6 frame counter size =1 - frame counter is 5B
                                                                                              //b7 reserved =0
   
   packetfunctions_reserveHeaderSize(msg,sizeof(uint8_t));
   *((uint8_t*)(msg->payload)) = temp_8b;
   
}