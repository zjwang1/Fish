import tushare as ts
import option
import json
from zjwang_strategy import Strategy
from history_sell import HistorySell
from t_process import T
from t_context import TContext

if __name__ == '__main__':
    args = option.parser.parse_args()
    quote = {}
    quote['Symbol'] = args.code
    quote['Name'] = args.name
    start_date = args.start_date
    end_date = args.end_date
    average_price = args.average_price
    total_num = args.total_num
    t_num = args.t_num
    t_gap = args.t_gap
    print("quote is {}".format(quote))
    #strategy = Strategy(average_price = average_price, total_num = total_num, t_num = t_num, t_gap = t_gap)
    t_context = TContext()
    history_sell = HistorySell(t_context, t_list = [20, 20, 20])
    t = T(history_sell)
    try:
        profit = 0.0
        df = ts.get_hist_data(quote['Symbol'][0:6],start=start_date,end=end_date)
        rjson = json.loads(df.to_json())
        dates = list(rjson["open"].keys())
        dates.sort()
        for date in dates:
            #　处理今天的t
            profit += t.in_(rjson["open"][date], rjson["low"][date], t_gap, date)
            #profit += t.in_2(rjson["open"][date], rjson["close"][date], date)
            #profit += t.re_in_2(rjson["low"][date], t_gap, date)
            profit += t.re_in_(rjson["low"][date], t_gap, date)
            #strategy.run(rjson["open"][date], rjson["low"][date])
            # print(date)
            '''d = {'Symbol': quote['Symbol']}
            d['Date'] = date
            d['Open'] = rjson["open"][date]
            d['Close'] = rjson["close"][date]
            d['High'] = rjson["high"][date]
            d['Low'] = rjson["low"][date]
            d['Volume'] = rjson["volume"][date]
            d['Price_Change'] =rjson["price_change"][date]
            d['P_Change'] = rjson["p_change"][date]
            d['MA_5'] = rjson["ma5"][date]
            d['MA_10'] = rjson["ma10"][date]
            d['MA_20'] = rjson["ma20"][date]
            d['V_MA_5'] = rjson["v_ma5"][date]
            d['V_MA_10'] = rjson["v_ma10"][date]
            d['V_MA_20'] = rjson["v_ma20"][date]'''
        #strategy.show()
        #print('T飞手数是 {}'.format(len(history_sell.get_all_fly())))
        #t.show()
        print('------------------------------------------------')
        t_context.show_trace()
        print('收益是 {}'.format(profit))
        print('T飞手数是 {}'.format(len(history_sell.get_all_fly())))
    except :
        print("Error: Failed to load stock data... " + quote['Symbol'] + "/" + quote['Name'] + "\n")