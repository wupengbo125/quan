# 聚宽A股量化交易策略 - 最终版
# 基于多因子选股和趋势跟踪的量化策略

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
    g.stock_num = 10
    
    # 设置行业分散参数
    g.max_industry_ratio = 0.3  # 单个行业最大占比
    
    # 设置风险控制参数
    g.max_drawdown_limit = 0.15  # 最大回撤限制
    g.position_limit = 0.9       # 最大仓位限制
    
    # 设置交易周期
    run_daily(trade, time='open')
    run_daily(market_close, time='close')
    run_daily(risk_management, time='14:30')  # 盘中风险控制

# 交易函数
def trade(context):
    # 获取当前日期
    current_dt = context.current_dt
    
    # 市场趋势判断
    if not market_trend_filter(current_dt):
        # 市场趋势不好，清仓
        clear_position(context)
        return
    
    # 获取股票池
    stock_list = get_index_stocks(g.security_pool)
    
    # 过滤ST股票
    stock_list = [stock for stock in stock_list if not is_st_stock(stock)]
    
    # 过滤停牌股票
    stock_list = [stock for stock in stock_list if not is_suspended(stock)]
    
    # 过滤次新股（上市不足60天）
    stock_list = filter_new_stocks(stock_list, current_dt)
    
    # 获取因子评分
    factor_scores = calculate_factor_scores(stock_list, current_dt)
    
    # 如果没有符合条件的股票，清仓
    if len(factor_scores) == 0:
        clear_position(context)
        return
    
    # 行业分散处理
    selected_stocks = select_stocks_with_industry_diversity(factor_scores, g.stock_num)
    
    # 如果没有选出股票，清仓
    if len(selected_stocks) == 0:
        clear_position(context)
        return
    
    # 调整仓位
    adjust_position(context, selected_stocks)

# 市场趋势过滤器
def market_trend_filter(current_dt):
    try:
        # 计算沪深300指数的20日均线
        hs300_price = get_price('000300.XSHG', end_date=current_dt, count=20, frequency='1d', fields=['close'])
        
        # 检查是否有足够的数据
        if len(hs300_price) < 20:
            return True  # 数据不足时默认允许交易
            
        ma20 = hs300_price['close'].mean()
        
        # 获取当前价格
        current_price = hs300_price['close'].iloc[-1]
        
        # 趋势判断：当前价格在均线上方即可
        if current_price > ma20:
            return True
        else:
            return False
    except:
        # 发生异常时默认允许交易
        return True

# 过滤次新股
def filter_new_stocks(stock_list, date):
    filtered_stocks = []
    for stock in stock_list:
        try:
            # 获取股票上市日期
            info = get_security_info(stock)
            if info and (date - info.start_date).days > 60:  # 上市超过60天
                filtered_stocks.append(stock)
        except:
            # 发生异常时保留股票
            filtered_stocks.append(stock)
    return filtered_stocks

# 计算因子评分
def calculate_factor_scores(stock_list, date):
    try:
        # 获取基本面数据
        q = query(
            valuation.code,
            valuation.market_cap,           # 市值因子
            valuation.pb_ratio,             # 价值因子
            valuation.pe_ratio,             # 价值因子
            indicator.roe,                  # 质量因子
            indicator.inc_return,           # 成长因子
            indicator.gross_profit_margin,  # 质量因子
            indicator.eps                   # 盈利因子
        ).filter(
            valuation.code.in_(stock_list)
        )
        
        df = get_fundamentals(q, date=date)
        
        # 检查是否有数据
        if len(df) == 0:
            return pd.DataFrame()
        
        # 处理空值
        df = df.dropna()
        
        # 检查处理空值后是否还有数据
        if len(df) == 0:
            return pd.DataFrame()
        
        # 标准化因子
        factors = ['market_cap', 'pb_ratio', 'pe_ratio', 'roe', 'inc_return', 'gross_profit_margin', 'eps']
        for factor in factors:
            if factor in df.columns and df[factor].std() > 0:
                df[factor] = (df[factor] - df[factor].mean()) / df[factor].std()
        
        # 计算综合评分
        df['score'] = 0
        
        # 小市值偏好
        if 'market_cap' in df.columns:
            df['score'] += -df['market_cap'] * 0.25
        
        # 低PB偏好
        if 'pb_ratio' in df.columns:
            df['score'] += -df['pb_ratio'] * 0.15
            
        # 低PE偏好
        if 'pe_ratio' in df.columns:
            df['score'] += -df['pe_ratio'] * 0.1
            
        # 高ROE偏好
        if 'roe' in df.columns:
            df['score'] += df['roe'] * 0.2
            
        # 高成长偏好
        if 'inc_return' in df.columns:
            df['score'] += df['inc_return'] * 0.1
            
        # 高毛利率偏好
        if 'gross_profit_margin' in df.columns:
            df['score'] += df['gross_profit_margin'] * 0.1
            
        # 高EPS偏好
        if 'eps' in df.columns:
            df['score'] += df['eps'] * 0.1
        
        return df
    except:
        # 发生异常时返回空DataFrame
        return pd.DataFrame()

# 行业分散选股
def select_stocks_with_industry_diversity(factor_scores, num):
    try:
        # 检查输入数据
        if len(factor_scores) == 0:
            return []
            
        # 获取股票行业信息
        industry_dict = {}
        for code in factor_scores['code']:
            try:
                industry_info = get_industry(code)
                if code in industry_info and 'sw_l1' in industry_info[code]:
                    industry = industry_info[code]['sw_l1']['industry_name']
                else:
                    industry = '其他'
                industry_dict[code] = industry
            except:
                industry_dict[code] = '其他'
        
        factor_scores['industry'] = factor_scores['code'].map(industry_dict)
        
        # 按评分排序
        factor_scores = factor_scores.sort_values('score', ascending=False)
        
        # 简化选股逻辑：直接选取评分最高的股票，但注意行业分散
        selected_stocks = []
        industry_count = {}
        
        for _, row in factor_scores.iterrows():
            if len(selected_stocks) >= num:
                break
                
            code = row['code']
            industry = row['industry']
            
            # 检查行业占比是否已达到上限
            industry_ratio = industry_count.get(industry, 0) / max(num, 1)
            if industry_ratio < g.max_industry_ratio or len(selected_stocks) < 3:  # 前3只股票不限制行业
                selected_stocks.append(code)
                industry_count[industry] = industry_count.get(industry, 0) + 1
        
        return selected_stocks
    except:
        # 发生异常时返回空列表
        return []

# 调整仓位
def adjust_position(context, selected_stocks):
    try:
        # 获取当前持仓
        current_holdings = list(context.portfolio.positions.keys())
        
        # 卖出不在选股列表中的股票
        for stock in current_holdings:
            if stock not in selected_stocks:
                order_target(stock, 0)
        
        # 买入新的选股
        if len(selected_stocks) > 0:
            # 等权分配资金
            cash_per_stock = context.portfolio.available_cash / len(selected_stocks)
            
            for stock in selected_stocks:
                try:
                    # 获取价格数据
                    current_dt = context.current_dt
                    price_data = get_price(stock, end_date=current_dt, count=1, frequency='1d', fields=['close'])
                    if len(price_data) > 0:
                        price = price_data['close'].iloc[-1]
                        if price > 0 and not np.isnan(price):
                            # 计算购买数量（100股整数倍）
                            amount = int(cash_per_stock / price / 100) * 100
                            
                            # 避免重复下单
                            current_position = context.portfolio.positions[stock].total_amount if stock in context.portfolio.positions else 0
                            if amount > current_position:
                                order(stock, amount - current_position)
                except:
                    # 发生异常时跳过该股票
                    continue
    except:
        # 发生异常时不进行交易
        pass

# 清仓
def clear_position(context):
    try:
        for stock in list(context.portfolio.positions.keys()):
            order_target(stock, 0)
    except:
        # 发生异常时忽略
        pass

# 风险管理
def risk_management(context):
    try:
        # 计算账户最大回撤
        portfolio_value = context.portfolio.total_value
        max_value = context.portfolio.starting_cash
        
        # 简化的回撤计算
        if portfolio_value < max_value * (1 - g.max_drawdown_limit):
            # 回撤过大，减仓
            for stock in list(context.portfolio.positions.keys()):
                try:
                    current_amount = context.portfolio.positions[stock].total_amount
                    order_target(stock, int(current_amount * 0.5))  # 减持50%
                except:
                    # 发生异常时跳过
                    continue
    except:
        # 发生异常时忽略
        pass

# 收盘后运行
def market_close(context):
    try:
        # 记录日志
        log.info("当前持仓: {}".format(list(context.portfolio.positions.keys())))
        log.info("账户总资产: {:.2f}元".format(context.portfolio.total_value))
        log.info("账户收益率: {:.2f}%".format((context.portfolio.total_value / context.portfolio.starting_cash - 1) * 100))
    except:
        # 发生异常时忽略
        pass