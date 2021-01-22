import tushare as ts
import option
import json
from zjwang_strategy import Strategy

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
    strategy = Strategy(average_price = average_price, total_num = total_num, t_num = t_num, t_gap = t_gap)
    try:
        df = ts.get_hist_data(quote['Symbol'][0:6],start=start_date,end=end_date)
        rjson = json.loads(df.to_json())
        dates = rjson["open"].keys()
        for date in dates:
            strategy.run(rjson["open"][date], rjson["low"][date])
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
        strategy.show()
    except:
        print("Error: Failed to load stock data... " + quote['Symbol'] + "/" + quote['Name'] + "\n")