# 聚宽A股量化交易策略 - 诊断版
# 详细诊断交易问题的版本

import jqdata
from kuanke.wizard import *
import pandas as pd
import numpy as np
from datetime import datetime

# 初始化函数
def initialize(context):
    log.info("=== 策略初始化 ===")
    
    # 设置基准收益
    set_benchmark('000300.XSHG')
    log.info("设置基准收益: 000300.XSHG")
    
    # 开启动态复权模式
    set_option('use_real_price', True)
    log.info("开启动态复权模式")
    
    # 设置成交量比例
    set_option('order_volume_ratio', 1)
    log.info("设置成交量比例: 1")
    
    # 设置滑点
    set_slippage(FixedSlippage(0.002))
    log.info("设置滑点: 0.002")
    
    # 设置手续费
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    log.info("设置手续费: 买入0.0003, 卖出0.0013, 最低5元")
    
    # 设置交易周期
    run_daily(trade, time='09:35')
    run_daily(market_close, time='close')
    
    log.info("=== 初始化完成 ===")

# 诊断交易函数
def trade(context):
    log.info("=== 开始诊断交易 ===")
    
    try:
        # 获取当前日期
        current_dt = context.current_dt
        log.info("当前日期: {}".format(current_dt))
        
        # 检查账户状态
        log.info("账户初始资金: {:.2f}元".format(context.portfolio.starting_cash))
        log.info("账户总资产: {:.2f}元".format(context.portfolio.total_value))
        log.info("可用现金: {:.2f}元".format(context.portfolio.available_cash))
        log.info("当前持仓: {}".format(list(context.portfolio.positions.keys())))
        
        # 检查是否有足够的资金进行交易
        if context.portfolio.available_cash < 1000:
            log.info("可用现金不足1000元，无法交易")
            return
            
        # 获取股票池 - 使用更简单的股票池
        stock_list = ['000001.XSHE', '000002.XSHE', '600000.XSHG', '600036.XSHG']
        log.info("测试股票池: {}".format(stock_list))
        
        # 选择第一只非停牌股票
        selected_stock = None
        for stock in stock_list:
            try:
                # 检查是否停牌
                current_data = get_current_data()
                if stock in current_data:
                    is_paused = current_data[stock].is_paused
                    log.info("股票 {} 停牌状态: {}".format(stock, is_paused))
                    if not is_paused:
                        selected_stock = stock
                        log.info("选择交易股票: {}".format(selected_stock))
                        break
                else:
                    log.info("无法获取股票 {} 的状态信息".format(stock))
            except Exception as e:
                log.info("检查股票 {} 状态时出错: {}".format(stock, str(e)))
                continue
        
        if not selected_stock:
            log.info("没有找到可交易的股票")
            return
            
        # 获取价格数据
        log.info("开始获取价格数据")
        price_data = get_price(selected_stock, end_date=current_dt, count=1, frequency='1d', fields=['close', 'open', 'high', 'low'])
        log.info("价格数据获取完成，数据长度: {}".format(len(price_data)))
        
        if len(price_data) > 0 and len(price_data['close']) > 0:
            close_price = price_data['close'].iloc[-1]
            open_price = price_data['open'].iloc[-1]
            log.info("股票 {} 收盘价: {:.2f}, 开盘价: {:.2f}".format(selected_stock, close_price, open_price))
            
            if close_price > 0 and not np.isnan(close_price):
                # 计算购买数量
                cash_to_use = min(context.portfolio.available_cash * 0.1, 50000)  # 使用最多10%的现金，但不超过50000元
                amount = int(cash_to_use / close_price / 100) * 100
                log.info("计划购买金额: {:.2f}元, 计算数量: {}股".format(cash_to_use, amount))
                
                if amount >= 100:
                    # 执行交易前再次检查
                    log.info("交易前账户状态 - 可用现金: {:.2f}元".format(context.portfolio.available_cash))
                    log.info("准备下单: 买入 {} {}股".format(selected_stock, amount))
                    
                    # 尝试下单
                    order_result = order(selected_stock, amount)
                    log.info("下单结果: {}".format(order_result))
                    
                    # 检查订单状态
                    if order_result:
                        log.info("下单成功")
                    else:
                        log.info("下单失败")
                else:
                    log.info("计算出的购买数量不足100股，不进行交易")
            else:
                log.info("股票价格无效")
        else:
            log.info("无法获取有效的价格数据")
            
    except Exception as e:
        log.info("交易函数出错: {}".format(str(e)))
        import traceback
        log.info("错误详情: {}".format(traceback.format_exc()))
    
    log.info("=== 诊断交易结束 ===")

# 收盘后运行
def market_close(context):
    try:
        log.info("=== 收盘诊断 ===")
        log.info("当前持仓: {}".format(list(context.portfolio.positions.keys())))
        if context.portfolio.positions:
            for stock, position in context.portfolio.positions.items():
                log.info("股票 {} 持仓: {}股, 市值: {:.2f}元".format(stock, position.total_amount, position.value))
        log.info("账户总资产: {:.2f}元".format(context.portfolio.total_value))
        log.info("可用现金: {:.2f}元".format(context.portfolio.available_cash))
        log.info("账户收益率: {:.2f}%".format((context.portfolio.total_value / context.portfolio.starting_cash - 1) * 100))
        log.info("=== 收盘诊断结束 ===")
    except Exception as e:
        log.info("收盘函数出错: {}".format(str(e)))
        import traceback
        log.info("错误详情: {}".format(traceback.format_exc()))