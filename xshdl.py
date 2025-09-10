
# 导入函数库
from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
from datetime import time


# 初始化函数
def initialize(context):
    # 开启防未来函数
    set_option('avoid_future_data', True)
    # 设定基准
    # set_benchmark('000300.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 将滑点设置为百分0.23，也就是买卖滑点各0.14%
    set_slippage(PriceRelatedSlippage(0.23 / 100), type='stock')

    # 设置交易成本万分之三，不同滑点影响可在归因分析中查看
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=2.5 / 10000, close_commission=2.5 / 10000,
                             close_today_commission=0, min_commission=5), type='stock')
    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')
    # 初始化全局变量 bool
    g.no_trading_today_signal = False  # 是否为可交易日
    g.pass_april = True  # 是否四月空仓
    g.run_stoploss = True  # 是否进行止损
    # 全局变量list
    g.hold_list = []  # 当前持仓的全部股票
    g.yesterday_HL_list = []  # 记录持仓中昨日涨停的股票
    g.target_list = []
    g.not_buy_again = []
    # 全局变量float/str
    g.stock_num = 5
    # g.m_days = 5  # 取值参考天数
    g.up_price = 100  # 设置股票单价
    g.reason_to_sell = ''
    g.stoploss_strategy = 3  # 1为止损线止损，2为市场趋势止损, 3为联合1、2策略
    g.stoploss_limit = 0.1  # 止损线（股票成本价止损）
    g.stoploss_market = 0.5  # 市场趋势止损参数(指数平均股价涨跌幅，不是指数本身的)
    # 设置全局变量
    g.m_days = 25  # 计算动量的时间窗口
    g.etf_pool = ['399101.XSHE', '000300.XSHG','000015.XSHG']  # ETF池
    g.etf_names = {
        # '399986.XSHE': '中证银行',
        '000015.XSHG': '红利',
        # '399998.XSHE': '煤炭',
        # '000819.XSHG': '有色金属',
        '000300.XSHG': '沪深300',
        '399101.XSHE': '中小盘'
    }  # ETF中文名称映射

    # 设置交易运行时间
    run_daily(prepare_stock_list, '9:55')
    run_daily(sell_stocks, time='10:01')  # 止损函数
    run_daily(trade_afternoon, time='14:00', reference_security='399101.XSHE')  # 检查持仓中的涨停股是否需要卖出
    # 399401.XSHE, 000300.XSHG
    run_daily(close_account, '14:50')
    run_weekly(weekly_adjustment, 2, '10:00')

    run_weekly(print_position_info, 5, time='15:10', reference_security='000300.XSHG')


# 1-1 准备股票池
def prepare_stock_list(context):
    # 获取已持有列表
    g.hold_list = []
    for position in list(context.portfolio.positions.values()):
        stock = position.security
        g.hold_list.append(stock)
    # 获取昨日涨停列表
    if g.hold_list != []:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily',
                       fields=['close', 'high_limit', 'low_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_HL_list = list(df.code)
        log.info("昨日涨停列表", g.yesterday_HL_list)
    else:
        g.yesterday_HL_list = []
    # 判断今天是否为账户资金再平衡的日期
    g.no_trading_today_signal = today_is_between(context)

#  止盈止损10:01
def sell_stocks(context):
    if g.run_stoploss == True:
        if g.stoploss_strategy == 1:
            for stock in context.portfolio.positions.keys():
                # 股票盈利大于等于100%则卖出
                if context.portfolio.positions[stock].price >= context.portfolio.positions[stock].avg_cost * 2:
                    order_target_value(stock, 0)
                    log.debug("收益100%止盈,卖出{}".format(stock))
                # 止损
                elif context.portfolio.positions[stock].price < context.portfolio.positions[stock].avg_cost * (
                        1 - g.stoploss_limit):
                    order_target_value(stock, 0)
                    log.debug("收益止损,卖出{}".format(stock))
                    g.reason_to_sell = 'stoploss'
        elif g.stoploss_strategy == 2:
            stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date,
                                 frequency='daily', fields=['close', 'open'], count=1, panel=False)
            # down_ratio = (stock_df['close'] / stock_df['open'] < 1).sum() / len(stock_df)
            down_ratio = abs((stock_df['close'] / stock_df['open'] - 1).mean())
            if down_ratio >= g.stoploss_market:
                g.reason_to_sell = 'stoploss'
                log.debug("大盘惨跌,平均降幅{:.2%}".format(down_ratio))
                for stock in context.portfolio.positions.keys():
                    order_target_value(stock, 0)
        elif g.stoploss_strategy == 3:
            stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date,
                                 frequency='daily', fields=['close', 'open'], count=1, panel=False)
            down_ratio = abs((stock_df['close'] / stock_df['open'] - 1).mean())
            log.info("深证中小板指数成分股涨跌幅{:.2%}".format(down_ratio))
            if down_ratio >= g.stoploss_market:
                g.reason_to_sell = 'stoploss'
                log.debug("深证中小板指数成分股止损了,平均涨跌幅{:.2%}".format(down_ratio))
                for stock in context.portfolio.positions.keys():
                    order_target_value(stock, 0)
                    # 检查是否成功卖出
                    if stock not in context.portfolio.positions:
                        log.info(f"10:00深证中小板指数成分股止损了，成功清仓股票：{stock}")
                    else:
                        log.info(f"10:00深证中小板指数成分股止损了，今天买入的股票：{stock}，下次止损卖出")
            else:
                for stock in context.portfolio.positions.keys():
                    current_price = context.portfolio.positions[stock].price
                    avg_cost = context.portfolio.positions[stock].avg_cost
                    # 计算跌幅
                    drop_ratio = (avg_cost - current_price) / avg_cost
                    if current_price < avg_cost * (
                            1 - g.stoploss_limit):
                        order_target_value(stock, 0)
                        log.debug("股票[{}]止损卖出，跌幅为{:.2%}".format(stock, drop_ratio))
                        g.reason_to_sell = 'stoploss'



#  下午检查交易
def trade_afternoon(context):
    if g.no_trading_today_signal == False:
        check_limit_up(context)
        check_remain_amount(context)

# 4-2 清仓后次日资金可转
def close_account(context):
    if g.no_trading_today_signal == True:
        if len(g.hold_list) != 0:
            for stock in g.hold_list:
                position = context.portfolio.positions[stock]
                close_position(position)
                log.info("卖出[%s]" % (stock))

# 1-3 整体调整持仓
def weekly_adjustment(context):
    if g.no_trading_today_signal == False:
        # 获取应买入列表
        rank_list, score_df = get_rank(g.etf_pool)
        if rank_list[0] != '399101.XSHE':
            log.info("第一名不是中小盘，清仓处理")
            for stock in context.portfolio.positions.keys():
                order_target_value(stock, 0)
                # 检查是否成功卖出
                if stock not in context.portfolio.positions:
                    log.info(f"10:00动量止损了，成功清仓股票：{stock}")
                else:
                    log.info(f"10:00动量止损了，今天买入的股票：{stock}，下次止损卖出")
            return
        g.not_buy_again = []
        g.target_list = get_stock_list(context)
        target_list = filter_not_buy_again(g.target_list)
        target_list = filter_paused_stock(target_list)
        target_list = filter_limitup_stock(context, target_list)
        target_list = filter_limitdown_stock(context, target_list)
        target_list = filter_highprice_stock(context, target_list)
        target_list = target_list[:g.stock_num]
        log.info(str(target_list))
        log.info("10:00最终筛选后的应该买入股票列表:")
        for stock in target_list:
            log.info(stock)

        # print(day_of_week)
        # print(type(day_of_week))
        # 调仓卖出
        for stock in g.hold_list:
            if (stock not in target_list) and (stock not in g.yesterday_HL_list):
                log.info("卖出[%s]" % (stock))
                position = context.portfolio.positions[stock]
                close_position(position)
            else:
                log.info("已持有[%s]" % (stock))
        # 调仓买入
        buy_security(context, target_list)
        # 记录已买入股票
        for position in list(context.portfolio.positions.values()):
            stock = position.security
            g.not_buy_again.append(stock)


def print_position_info(context):
    for position in list(context.portfolio.positions.values()):
        securities = position.security
        cost = position.avg_cost
        price = position.price
        ret = 100 * (price / cost - 1)
        value = position.value
        amount = position.total_amount
        print('代码:{}'.format(securities))
        print('成本价:{}'.format(format(cost, '.2f')))
        print('现价:{}'.format(price))
        print('收益率:{}%'.format(format(ret, '.2f')))
        print('持仓(股):{}'.format(amount))
        print('市值:{}'.format(format(value, '.2f')))
        print('———————————————————————————————————')
    print('———————————————————————————————————————分割线————————————————————————————————————————')


# 1-4 调整昨日涨停股票，开板就卖
def check_limit_up(context):
    now_time = context.current_dt
    if g.yesterday_HL_list != []:
        # 对昨日涨停股票观察到尾盘如不涨停则提前卖出，如果涨停即使不在应买入列表仍暂时持有
        for stock in g.yesterday_HL_list:
            current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close', 'high_limit'],
                                     skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)
            if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
                log.info("[%s]涨停打开板（不再继续涨停），卖出" % (stock))
                position = context.portfolio.positions[stock]
                close_position(position)
                g.reason_to_sell = 'limitup'
            else:
                log.info("[%s]涨停，虽然不在买入列表，但是可以继续持有" % (stock))


# 1-5 如果昨天有股票卖出或者买入失败，剩余的金额今天早上买入
def check_remain_amount(context):
    if g.reason_to_sell is 'limitup':  # 判断提前售出原因，如果是涨停售出则次日再次交易，如果是止损售出则不交易
        g.hold_list = []
        for position in list(context.portfolio.positions.values()):
            stock = position.security
            g.hold_list.append(stock)
        log.info("当前持仓股票列表", g.hold_list)
        if len(g.hold_list) < g.stock_num:
            target_list = g.target_list
            log.info("14:00初步筛选的50个股票列表", target_list)
            # 剔除本周买入过的股票，不再买入
            target_list = filter_not_buy_again(target_list)
            log.info("14:00最终的股票列表，就是目标持仓数量", target_list)
            target_list = target_list[:min(g.stock_num, len(target_list))]
            log.info('有余额可用,补充产品买入' + str(round((context.portfolio.cash), 2)) + '元。' + str(target_list))
            buy_security(context, target_list)
        g.reason_to_sell = ''
    else:
        log.info('虽然有余额可用，但是为止损后余额，下周再交易')
        g.reason_to_sell = ''

def get_stock_list(context):
    final_list = []
    MKT_index = '399101.XSHE'
    initial_list = get_index_stocks(MKT_index)
    initial_list = filter_new_stock(context, initial_list)
    initial_list = filter_kcbj_stock(initial_list)
    initial_list = filter_st_stock(initial_list)

    # 添加财务指标筛选条件
    q = query(
        valuation.code,
        valuation.market_cap,
        # income.net_profit,  # 净利润
        # income.total_operating_revenue,  # 营业收入
        # income.np_parent_company_owners  # 归属于母公司所有者的净利润
    ).filter(
        valuation.code.in_(initial_list),
        valuation.market_cap.between(5, 30),
        # income.net_profit > 0,  # 净利润大于0
        # income.total_operating_revenue > 100000000,  # 营业收入大于1亿
        # income.np_parent_company_owners > 0  # 归属于母公司所有者的净利润大于0
    ).order_by(
        valuation.market_cap.asc()
    )

    df_fun = get_fundamentals(q)
    df_fun = df_fun[:100]

    initial_list = list(df_fun.code)
    initial_list = filter_paused_stock(initial_list)
    initial_list = filter_limitup_stock(context, initial_list)
    initial_list = filter_limitdown_stock(context, initial_list)
    # print('initial_list中含有{}个元素'.format(len(initial_list)))
    q = query(valuation.code, valuation.market_cap).filter(valuation.code.in_(initial_list)).order_by(
        valuation.market_cap.asc())
    df_fun = get_fundamentals(q)
    df_fun = df_fun[:50]
    final_list = list(df_fun.code)
    return final_list


# 2-1 过滤停牌股票
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]


# 2-2 过滤ST及其他具有退市标签的股票
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]


# 2-3 过滤科创北交股票
def filter_kcbj_stock(stock_list):
    for stock in stock_list[:]:
        if stock[0] == '4' or stock[0] == '8' or stock[:2] == '68':
            stock_list.remove(stock)
    return stock_list


# 2-4 过滤涨停的股票
def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] < current_data[stock].high_limit]


# 2-5 过滤跌停的股票
def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] > current_data[stock].low_limit]


# 2-6 过滤次新股
def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if
            not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]


# 2-6.5 过滤股价
def filter_highprice_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] <= g.up_price]


# 计算ETF的排名
def get_rank(etf_pool):
    score_list = []
    for etf in etf_pool:
        df = attribute_history(etf, g.m_days, '1d', ['close'])
        df['log'] = np.log(df.close)
        df['num'] = np.arange(len(df))
        slope, intercept = np.polyfit(df['num'], df['log'], 1)
        annualized_returns = math.pow(math.exp(slope), 250) - 1
        residuals = df['log'] - (slope * df['num'] + intercept)
        r_squared = 1 - (residuals ** 2).sum() / ((len(df) - 1) * np.var(df['log'], ddof=1))
        score = annualized_returns * r_squared
        score_list.append(score)

    # 创建得分DataFrame并排序
    score_df = pd.DataFrame(index=etf_pool, data={'score': score_list})
    score_df = score_df.sort_values(by='score', ascending=False)
    rank_list = list(score_df.index)

    # 打印每个ETF的得分
    log.info("今日ETF得分排名：")
    for etf in rank_list:
        etf_name = g.etf_names.get(etf, '未知')  # 获取中文名称
        log.info(f"{etf}（{etf_name}）: {score_df.loc[etf, 'score']:.6f}")

    # 记录部分ETF的得分
    # record(中证银行=round(score_df.loc['399986.XSHE', 'score'], 2))
    record(红利=round(score_df.loc['000015.XSHG', 'score'], 2))
    # record(煤炭=round(score_df.loc['399998.XSHE', 'score'], 2))
    # record(有色金属=round(score_df.loc['000819.XSHG', 'score'], 2))
    record(沪深300=round(score_df.loc['000300.XSHG', 'score'], 2))

    record(中小盘=round(score_df.loc['399101.XSHE', 'score'], 2))

    return rank_list, score_df


# 2-7 删除--本周买入过的股票
def filter_not_buy_again(stock_list):
    log.info("14:00本周已经买入过的股票列表：{}".format(g.not_buy_again))
    return [stock for stock in stock_list if stock not in g.not_buy_again]


# 3-1 交易模块-自定义下单
def order_target_value_(security, value):
    if value == 0:
        pass
        # log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
    return order_target_value(security, value)


# 3-2 交易模块-开仓
def open_position(security, value):
    order = order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False


# 3-3 交易模块-平仓
def close_position(position):
    security = position.security
    order = order_target_value_(security, 0)  # 可能会因停牌失败
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    return False


# 3-4 买入模块
def buy_security(context, target_list):
    # 调仓买入
    position_count = len(context.portfolio.positions)
    target_num = len(target_list)
    log.info("当前持仓数量：%d，目标持仓数量：%d" % (position_count, target_num))
    if target_num > position_count:
        value = context.portfolio.cash / (target_num - position_count)
        log.info("剩余资金：%f，目标买入金额：%f" % (context.portfolio.cash, value))
        for stock in target_list:
            if stock not in context.portfolio.positions or context.portfolio.positions[stock].total_amount == 0:
                if open_position(stock, value):
                    log.info("买入[%s]（%s元）" % (stock, value))
                    g.not_buy_again.append(stock)  # 持仓清单，后续不希望再买入
                else:
                    log.info("未买入[%s]，原因：买入失败或资金不足" % stock)
            else:
                log.info("未买入[%s]，原因：已持有该股票" % stock)
            # 如果已达到目标持仓数量，停止买入
            if len(context.portfolio.positions) == target_num:
                break
    else:
        log.info("未执行买入操作，原因：目标持仓数量小于等于当前持仓数量")


# 4-1 判断今天是否为空仓的月份
def today_is_between(context):
    today = context.current_dt.strftime('%m-%d')
    month = context.current_dt.strftime('%m')
    # 修改为空仓的月份
    no_trading_months = []
    if g.pass_april is True:
        if month in no_trading_months:
            return True
        else:
            return False
    else:
        return False