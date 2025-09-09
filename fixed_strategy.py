# 聚宽A股量化交易策略 - 修复版
# 解决不交易问题的版本

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
    g.stock_num = 5
    
    # 设置行业分散参数
    g.max_industry_ratio = 0.3  # 单个行业最大占比
    
    # 设置风险控制参数
    g.max_drawdown_limit = 0.15  # 最大回撤限制
    g.position_limit = 0.9       # 最大仓位限制
    
    # 设置交易周期 - 在开盘后几分钟执行，确保数据可用
    run_daily(trade, time='09:35')
    run_daily(market_close, time='close')
    run_daily(risk_management, time='14:30')  # 盘中风险控制

# 检查是否为ST股票
def is_st_stock(stock):
    try:
        # 获取股票信息
        info = get_security_info(stock)
        if info and hasattr(info, 'display_name'):
            return 'ST' in info.display_name or '*ST' in info.display_name
        return False
    except:
        return False

# 检查是否停牌
def is_suspended(stock):
    try:
        # 获取股票停牌信息
        current_data = get_current_data()
        if stock in current_data:
            return current_data[stock].is_paused
        return True
    except:
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
            
        # 只取前20只股票进行测试
        if len(stock_list) > 20:
            stock_list = stock_list[:20]
            log.info("截取前20只股票进行测试")
            
        log.info("最终股票池数量: {}".format(len(stock_list)))
        
        # 获取因子评分
        factor_scores = calculate_factor_scores(stock_list, current_dt)
        
        # 如果没有符合条件的股票，清仓
        if len(factor_scores) == 0:
            log.info("没有符合条件的股票，清仓")
            clear_position(context)
            return
        
        # 选股
        selected_stocks = select_stocks_with_industry_diversity(factor_scores, g.stock_num)
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

# 计算因子评分
def calculate_factor_scores(stock_list, date):
    try:
        log.info("开始计算因子评分")
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
            log.info("基本面数据为空")
            return pd.DataFrame()
        
        # 处理空值
        df = df.dropna()
        
        # 检查处理空值后是否还有数据
        if len(df) == 0:
            log.info("处理空值后数据为空")
            return pd.DataFrame()
            
        log.info("获取到{}只股票的基本面数据".format(len(df)))
        
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
        
        log.info("因子评分计算完成")
        return df
    except Exception as e:
        # 发生异常时返回空DataFrame
        log.info("计算因子评分出错: {}".format(str(e)))
        return pd.DataFrame()

# 行业分散选股
def select_stocks_with_industry_diversity(factor_scores, num):
    try:
        log.info("开始行业分散选股")
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
        
        log.info("行业分散选股完成，选出{}只股票".format(len(selected_stocks)))
        return selected_stocks
    except Exception as e:
        # 发生异常时返回空列表
        log.info("行业分散选股出错: {}".format(str(e)))
        return []

# 调整仓位 - 修复版
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
                    
                    # 修复：使用正确的参数获取价格数据
                    price_data = get_price(stock, end_date=current_dt, count=1, frequency='1d', fields=['close'])
                    log.info("获取到价格数据，长度: {}".format(len(price_data)))
                    
                    if len(price_data) > 0 and len(price_data['close']) > 0:
                        price = price_data['close'].iloc[-1]
                        log.info("股票 {} 价格: {:.2f}".format(stock, price))
                        
                        if price > 0 and not np.isnan(price):
                            # 计算购买数量（100股整数倍）
                            amount = int(cash_per_stock / price / 100) * 100
                            log.info("计算出购买数量: {}".format(amount))
                            
                            if amount >= 100:  # 至少买100股
                                # 避免重复下单
                                current_position = context.portfolio.positions[stock].total_amount if stock in context.portfolio.positions else 0
                                target_amount = max(amount, current_position)
                                log.info("下单买入 {} 目标数量: {}股".format(stock, target_amount))
                                order_target(stock, target_amount)
                                log.info("下单完成")
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

# 风险管理
def risk_management(context):
    try:
        log.info("开始风险管理")
        # 计算账户最大回撤
        portfolio_value = context.portfolio.total_value
        max_value = context.portfolio.starting_cash
        
        # 简化的回撤计算
        if portfolio_value < max_value * (1 - g.max_drawdown_limit):
            log.info("触发最大回撤限制，开始减仓")
            # 回撤过大，减仓
            for stock in list(context.portfolio.positions.keys()):
                try:
                    current_amount = context.portfolio.positions[stock].total_amount
                    order_target(stock, int(current_amount * 0.5))  # 减持50%
                    log.info("减仓股票: {}，减持50%".format(stock))
                except Exception as e:
                    # 发生异常时跳过
                    log.info("减仓股票 {} 时出错: {}".format(stock, str(e)))
                    continue
        else:
            log.info("未触发风险控制")
    except Exception as e:
        log.info("风险管理出错: {}".format(str(e)))

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