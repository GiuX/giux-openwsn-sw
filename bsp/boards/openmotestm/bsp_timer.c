/**
\brief GINA-specific definition of the "bsp_timer" bsp module.

On GINA, we use timerB0 for the bsp_timer module.

\author Thomas Watteyne <watteyne@eecs.berkeley.edu>, March 2012.
\author Chang Tengfei <tengfei.chang@gmail.com>,  July 2012.
*/
#include "stm32f10x_rcc.h"
#include "stm32f10x_nvic.h"
#include "stm32f10x_tim.h"
#include "bsp_timer.h"
#include "board.h"
#include "board_info.h"

//=========================== defines =========================================

//=========================== variables =======================================

typedef struct {
   bsp_timer_cbt    cb;
   PORT_TIMER_WIDTH last_compare_value;
} bsp_timer_vars_t;

bsp_timer_vars_t bsp_timer_vars;

//=========================== prototypes ======================================

//=========================== public ==========================================

/**
\brief Initialize this module.

This functions starts the timer, i.e. the counter increments, but doesn't set
any compare registers, so no interrupt will fire.
*/
void bsp_timer_init() 
{
    // clear local variables
    memset(&bsp_timer_vars,0,sizeof(bsp_timer_vars_t));
   
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure ;
    TIM_OCInitTypeDef TIM_OCInitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;
    
    //��TIM2����ʱ��
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2 , ENABLE);

    //**************************************************************************
    //     ��ʱ��2���ã� 7199��Ƶ��TIM1_COUNTms�ж�һ�Σ����ϼ���
    //**************************************************************************
    TIM_TimeBaseStructure.TIM_Period = (uint16_t)TIM2_COUNT;
    TIM_TimeBaseStructure.TIM_Prescaler = 7199;    //10KHz
    TIM_TimeBaseStructure.TIM_ClockDivision = 0;
    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure); //��ʼ����ʱ��
    
    //TIM2_OC1ģ������
    TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_Toggle;             //�ܽ����ģʽ����ת
    TIM_OCInitStructure.TIM_Pulse = 0;                           //��ת���ڣ�2000������
    TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable;   //ʹ��TIM1_CH1ͨ��
    TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High;       //���Ϊ���߼�
    TIM_OC1Init(TIM2, &TIM_OCInitStructure);                        //д������
   /* 
    //���ж�
    TIM_ClearFlag(TIM2, TIM_FLAG_CC1);
    TIM_ITConfig(TIM2, TIM_IT_CC1, ENABLE); //����ʱ���ж�
    */
    TIM_Cmd(TIM2, ENABLE); //ʹ�ܶ�ʱ��
    
         // ʹ��TIM1�Ƚ��ж�
    NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQChannel;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

/**
\brief Register a callback.

\param cb The function to be called when a compare event happens.
*/
void bsp_timer_set_callback(bsp_timer_cbt cb)
{
   bsp_timer_vars.cb   = cb;
}

/**
\brief Reset the timer.

This function does not stop the timer, it rather resets the value of the
counter, and cancels a possible pending compare event.
*/
void bsp_timer_reset()
{
    // reset compare
    //TIM1_OC1ģ������
    TIM_SetCompare1(TIM2,0);
  
    TIM_ClearFlag(TIM2, TIM_FLAG_CC1);
    TIM_ITConfig(TIM2, TIM_IT_CC1, ENABLE); //����ʱ���ж�
    // reset timer
    TIM_SetCounter(TIM2,0);
    // record last timer compare value
    bsp_timer_vars.last_compare_value =  0;
}

/**
\brief Schedule the callback to be called in some specified time.

The delay is expressed relative to the last compare event. It doesn't matter
how long it took to call this function after the last compare, the timer will
expire precisely delayTicks after the last one.

The only possible problem is that it took so long to call this function that
the delay specified is shorter than the time already elapsed since the last
compare. In that case, this function triggers the interrupt to fire right away.

This means that the interrupt may fire a bit off, but this inaccuracy does not
propagate to subsequent timers.

\param delayTicks Number of ticks before the timer expired, relative to the
                  last compare event.
*/
void bsp_timer_scheduleIn(PORT_TIMER_WIDTH delayTicks) 
{
   PORT_TIMER_WIDTH newCompareValue;
   PORT_TIMER_WIDTH temp_last_compare_value;
   
   temp_last_compare_value = bsp_timer_vars.last_compare_value;
   
   newCompareValue = bsp_timer_vars.last_compare_value+delayTicks;
   bsp_timer_vars.last_compare_value = newCompareValue;
   
   if (delayTicks < (TIM_GetCounter(TIM2)-temp_last_compare_value)) 
   {
      // setting the interrupt flag triggers an interrupt
      TIM_ClearFlag(TIM2, TIM_FLAG_CC1);
      TIM_ITConfig(TIM2, TIM_IT_CC1, ENABLE); //����ʱ���ж�
   } 
   else
   {
      // this is the normal case, have timer expire at newCompareValue
      TIM_SetCompare1(TIM2,newCompareValue);
      TIM_ClearFlag(TIM2, TIM_FLAG_CC1);
      TIM_ITConfig(TIM2, TIM_IT_CC1, ENABLE); //����ʱ���ж�
   }
}

/**
\brief Cancel a running compare.
*/
void bsp_timer_cancel_schedule() 
{
    TIM_SetCompare1(TIM2,0);
    TIM_ITConfig(TIM2, TIM_IT_CC1, DISABLE); //�ض�ʱ���ж�
}

/**
\brief Return the current value of the timer's counter.

\returns The current value of the timer's counter.
*/
PORT_TIMER_WIDTH bsp_timer_get_currentValue() 
{
   return TIM_GetCounter(TIM2);
}

//=========================== private =========================================

//=========================== interrupt handlers ==============================

uint8_t bsp_timer_isr()
{
   // call the callback
   bsp_timer_vars.cb();
   // kick the OS
   return 1;
}