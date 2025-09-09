# 聚宽A股量化交易策略 - 最简测试版
# 用于测试交易功能是否正常

import jqdata
from kuanke.wizard import *
import pandas as pd
import numpy as np
from datetime import datetime

# 初始化函数
def initialize(context):
    # 设置基准收益
    set_benchmark('000300.XSHG')
    
    # 开启动态复权模式
    set_option('use_real_price', True)
    
    # 设置成交量比例
    set_option('order_volume_ratio', 1)
    
    # 设置滑点
    set_slippage(FixedSlippage(0.002))
    
    # 设置手续费
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    
    # 设置交易周期 - 在开盘后几分钟执行
    run_daily(trade, time='09:35')
    run_daily(market_close, time='close')

# 最简交易函数
def trade(context):
    log.info("=== 开始最简交易测试 ===")
    
    try:
        # 获取当前日期
        current_dt = context.current_dt
        log.info("当前日期: {}".format(current_dt))
        
        # 简单获取一只股票测试交易
        stock = '000001.XSHE'  # 平安银行
        log.info("测试交易股票: {}".format(stock))
        
        # 检查是否停牌
        current_data = get_current_data()
        if stock in current_data and current_data[stock].is_paused:
            log.info("股票 {} 停牌，无法交易".format(stock))
            return
            
        # 获取价格
        price_data = get_price(stock, end_date=current_dt, count=1, frequency='1d', fields=['close'])
        if len(price_data) > 0 and len(price_data['close']) > 0:
            price = price_data['close'].iloc[-1]
            log.info("股票 {} 价格: {:.2f}".format(stock, price))
            
            if price > 0 and not np.isnan(price):
                # 使用固定金额买入
                cash = context.portfolio.available_cash
                log.info("可用现金: {:.2f}元".format(cash))
                
                if cash > price * 100:  # 确保有足够的钱买100股
                    # 直接下单买入100股
                    log.info("下单买入 {} 100股，价格: {:.2f}".format(stock, price))
                    order(stock, 100)
                    log.info("下单完成")
                else:
                    log.info("现金不足，无法买入")
            else:
                log.info("股票价格无效")
        else:
            log.info("无法获取股票价格数据")
            
    except Exception as e:
        log.info("交易函数出错: {}".format(str(e)))
        import traceback
        log.info("错误详情: {}".format(traceback.format_exc()))

# 收盘后运行
def market_close(context):
    try:
        log.info("=== 收盘信息 ===")
        log.info("当前持仓: {}".format(list(context.portfolio.positions.keys())))
        log.info("账户总资产: {:.2f}元".format(context.portfolio.total_value))
        log.info("可用现金: {:.2f}元".format(context.portfolio.available_cash))
        log.info("账户收益率: {:.2f}%".format((context.portfolio.total_value / context.portfolio.starting_cash - 1) * 100))
    except Exception as e:
        log.info("收盘函数出错: {}".format(str(e)))