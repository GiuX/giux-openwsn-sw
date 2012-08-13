/**
\brief GINA-specific definition of the "uart" bsp module.

\author Thomas Watteyne <watteyne@eecs.berkeley.edu>, February 2012.
\author Chang Tengfei <tengfei.chang@gmail.com>,  July 2012.
*/

#include "stm32f10x_gpio.h"
#include "stm32f10x_rcc.h"
#include "stm32f10x_nvic.h"
#include "stm32f10x_usart.h"
#include "stdint.h"
#include "stdio.h"
#include "string.h"
#include "uart.h"
#include "leds.h"

//=========================== defines =========================================

//=========================== variables =======================================

typedef struct {
   uart_tx_cbt txCb;
   uart_rx_cbt rxCb;
} uart_vars_t;

uart_vars_t uart_vars;

//=========================== prototypes ======================================

//=========================== public ==========================================

void uart_init() 
{
    // reset local variables
    memset(&uart_vars,0,sizeof(uart_vars_t));
  
    USART_InitTypeDef USART_InitStructure;

    //ʹ�ܴ���1ʱ��
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1, ENABLE);
  
    //******************************************************************************
    //    ����1������ʼ�����岿��,����1����Ϊ38400 �� 8 ��1 ��N  �����жϷ�ʽ
    //******************************************************************************  
    USART_InitStructure.USART_BaudRate = 38400; //�趨��������
    USART_InitStructure.USART_WordLength = USART_WordLength_8b; //�趨��������λ��
    USART_InitStructure.USART_StopBits = USART_StopBits_1;    //�趨ֹͣλ����
    USART_InitStructure.USART_Parity = USART_Parity_No ;      //����У��λ
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//������������
    USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;   //ʹ�ý��պͷ��͹��� 
    USART_Init(USART1, &USART_InitStructure);  //��ʼ������1
  
    uart_enableInterrupts();
  
    USART_Cmd(USART1, ENABLE);  //ʹ�ܴ���1
  
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA , ENABLE);
  
    GPIO_InitTypeDef GPIO_InitStructure;              //����һ���ṹ��
  
    //******************************************************************************
    //  ����1��ʹ�ùܽ�������붨��
    //******************************************************************************
  
    // ����UART1 TX (PA.09)��Ϊ�����������
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;         //IO�ڵĵھŽ�
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz; //IO���ٶ�
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;   //IO�ڸ����������
    GPIO_Init(GPIOA, &GPIO_InitStructure);            //��ʼ������1���IO��

    // ���� USART1 Rx (PA.10)Ϊ�������� 
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;           //IO�ڵĵ�ʮ��
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz; //IO���ٶ�
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;//IO����������
    GPIO_Init(GPIOA, &GPIO_InitStructure);               //��ʼ������1����IO
  
    NVIC_InitTypeDef 	NVIC_InitStructure;
    //  NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);//��ռ���ȼ�2λ,�����ȼ�2λ
    NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQChannel;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 3;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 3;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

void uart_setCallbacks(uart_tx_cbt txCb, uart_rx_cbt rxCb) 
{
    uart_vars.txCb = txCb;
    uart_vars.rxCb = rxCb;
}

void uart_enableInterrupts()
{
    USART_ITConfig(USART1, USART_IT_TC, ENABLE);
    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);
    USART_ClearFlag(USART1, USART_FLAG_TC);
}

void uart_disableInterrupts()
{
    USART_ITConfig(USART1, USART_IT_TC, DISABLE);
    USART_ITConfig(USART1, USART_IT_RXNE, DISABLE);
}

void uart_clearRxInterrupts()
{
    USART_ClearFlag(USART1,USART_FLAG_RXNE);
}

void uart_clearTxInterrupts()
{
    USART_ClearFlag(USART1,USART_FLAG_TC);
}

void uart_writeByte(uint16_t byteToWrite)
{
    USART_SendData(USART1,byteToWrite);
    while(USART_GetFlagStatus(USART1,USART_FLAG_TXE) == RESET);
}

uint16_t uart_readByte()
{
    uint16_t temp;
    temp = USART_ReceiveData(USART1);
    return temp;
}

//=========================== interrupt handlers ==============================

uint8_t uart_isr_tx() 
{
    uart_vars.txCb();
    return 0;
}

uint8_t uart_isr_rx() 
{
    uart_vars.rxCb();
    return 0;
}