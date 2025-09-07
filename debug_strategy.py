# 聚宽A股量化交易策略 - 调试版
# 带详细日志的调试版本，帮助诊断交易问题

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
    
    # 设置股票池 - 沪深300
    g.security_pool = '000300.XSHG'
    
    # 设置持仓数量
    g.stock_num = 5  # 减少到5只便于调试
    
    # 设置行业分散参数
    g.max_industry_ratio = 0.3  # 单个行业最大占比
    
    # 设置风险控制参数
    g.max_drawdown_limit = 0.15  # 最大回撤限制
    g.position_limit = 0.9       # 最大仓位限制
    
    # 设置交易周期
    run_daily(trade, time='open')
    run_daily(market_close, time='close')

# 检查是否为ST股票
def is_st_stock(stock):
    try:
        # 获取股票信息
        info = get_security_info(stock)
        if info and hasattr(info, 'display_name'):
            is_st = 'ST' in info.display_name or '*ST' in info.display_name
            log.info("股票 {} 是否为ST: {}".format(stock, is_st))
            return is_st
        log.info("股票 {} 无法获取ST信息".format(stock))
        return False
    except Exception as e:
        log.info("检查股票 {} 是否为ST时出错: {}".format(stock, str(e)))
        return False

# 检查是否停牌
def is_suspended(stock):
    try:
        # 获取股票停牌信息
        current_data = get_current_data()
        if stock in current_data:
            is_paused = current_data[stock].is_paused
            log.info("股票 {} 是否停牌: {}".format(stock, is_paused))
            return is_paused
        log.info("股票 {} 无法获取停牌信息".format(stock))
        return True
    except Exception as e:
        log.info("检查股票 {} 是否停牌时出错: {}".format(stock, str(e)))
        return True

# 交易函数
def trade(context):
    log.info("=== 开始交易 ===")
    
    try:
        # 获取当前日期
        current_dt = context.current_dt
        log.info("当前日期: {}".format(current_dt))
        
        # 市场趋势判断
        trend_ok = market_trend_filter(current_dt)
        log.info("市场趋势是否向好: {}".format(trend_ok))
        
        if not trend_ok:
            # 市场趋势不好，清仓
            log.info("市场趋势不好，清仓")
            clear_position(context)
            return
        
        # 获取股票池
        log.info("开始获取股票池")
        stock_list = get_index_stocks(g.security_pool)
        log.info("初始股票池数量: {}".format(len(stock_list)))
        
        if len(stock_list) == 0:
            log.info("股票池为空，无法交易")
            return
            
        # 过滤ST股票
        log.info("开始过滤ST股票")
        st_filtered_count = len(stock_list)
        stock_list = [stock for stock in stock_list if not is_st_stock(stock)]
        log.info("过滤ST股票后数量: {} -> {}".format(st_filtered_count, len(stock_list)))
        
        # 过滤停牌股票
        log.info("开始过滤停牌股票")
        suspended_filtered_count = len(stock_list)
        stock_list = [stock for stock in stock_list if not is_suspended(stock)]
        log.info("过滤停牌股票后数量: {} -> {}".format(suspended_filtered_count, len(stock_list)))
        
        if len(stock_list) == 0:
            log.info("过滤后股票池为空，无法交易")
            return
            
        # 只取前10只股票进行测试
        if len(stock_list) > 10:
            stock_list = stock_list[:10]
            log.info("截取前10只股票进行测试")
            
        log.info("最终股票池: {}".format(stock_list))
        
        # 简化策略：直接买入前几只股票
        selected_stocks = stock_list[:g.stock_num] if len(stock_list) >= g.stock_num else stock_list
        log.info("选股结果: {}".format(selected_stocks))
        
        # 调整仓位
        adjust_position(context, selected_stocks)
        
    except Exception as e:
        log.info("交易函数出错: {}".format(str(e)))

# 市场趋势过滤器
def market_trend_filter(current_dt):
    try:
        log.info("开始市场趋势判断")
        # 计算沪深300指数的20日均线
        hs300_price = get_price('000300.XSHG', end_date=current_dt, count=20, frequency='1d', fields=['close'])
        
        # 检查是否有足够的数据
        if len(hs300_price) < 20:
            log.info("沪深300数据不足20天，默认允许交易")
            return True  # 数据不足时默认允许交易
            
        ma20 = hs300_price['close'].mean()
        
        # 获取当前价格
        current_price = hs300_price['close'].iloc[-1]
        log.info("沪深300当前价格: {}, 20日均线: {}".format(current_price, ma20))
        
        # 趋势判断：当前价格在均线上方即可
        trend_ok = current_price > ma20
        log.info("趋势判断结果: {}".format(trend_ok))
        return trend_ok
    except Exception as e:
        log.info("市场趋势判断出错: {}，默认允许交易".format(str(e)))
        # 发生异常时默认允许交易
        return True

# 调整仓位
def adjust_position(context, selected_stocks):
    try:
        log.info("=== 开始调整仓位 ===")
        log.info("选股结果: {}".format(selected_stocks))
        
        # 获取当前持仓
        current_holdings = list(context.portfolio.positions.keys())
        log.info("当前持仓: {}".format(current_holdings))
        
        # 卖出不在选股列表中的股票
        for stock in current_holdings:
            if stock not in selected_stocks:
                log.info("卖出股票: {}".format(stock))
                order_target(stock, 0)
        
        # 买入新的选股
        if len(selected_stocks) > 0:
            # 等权分配资金
            cash_per_stock = context.portfolio.available_cash / len(selected_stocks)
            log.info("每只股票可用资金: {:.2f}元".format(cash_per_stock))
            
            for stock in selected_stocks:
                try:
                    log.info("处理股票: {}".format(stock))
                    # 获取价格数据
                    current_dt = context.current_dt
                    price_data = get_price(stock, end_date=current_dt, count=1, frequency='1d', fields=['close'])
                    log.info("获取到价格数据，长度: {}".format(len(price_data)))
                    
                    if len(price_data) > 0:
                        price = price_data['close'].iloc[-1]
                        log.info("股票 {} 价格: {:.2f}".format(stock, price))
                        
                        if price > 0 and not np.isnan(price):
                            # 计算购买数量（100股整数倍）
                            amount = int(cash_per_stock / price / 100) * 100
                            log.info("计算出购买数量: {}".format(amount))
                            
                            if amount >= 100:  # 至少买100股
                                # 避免重复下单
                                current_position = context.portfolio.positions[stock].total_amount if stock in context.portfolio.positions else 0
                                if amount > current_position:
                                    log.info("下单买入 {} {}股".format(stock, amount - current_position))
                                    order(stock, amount - current_position)
                                    log.info("下单完成")
                                else:
                                    log.info("无需买入，当前持仓已足够")
                            else:
                                log.info("计算出的数量不足100股，不买入")
                        else:
                            log.info("股票 {} 价格无效".format(stock))
                    else:
                        log.info("无法获取股票 {} 的价格数据".format(stock))
                except Exception as e:
                    log.info("处理股票 {} 时出错: {}".format(stock, str(e)))
                    continue
        else:
            log.info("选股为空，不进行买入操作")
    except Exception as e:
        log.info("调整仓位出错: {}".format(str(e)))

# 清仓
def clear_position(context):
    try:
        log.info("开始清仓")
        for stock in list(context.portfolio.positions.keys()):
            log.info("清仓股票: {}".format(stock))
            order_target(stock, 0)
    except Exception as e:
        log.info("清仓出错: {}".format(str(e)))

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