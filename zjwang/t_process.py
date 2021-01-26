class T(object):
    def __init__(self, history_sell):
        self.history_sell = history_sell
    
    def re_in_(self, low: float, t_gap: float, date):
        re_in_profit = 0.0
        t_fly = self.history_sell.get_all_fly()
        for index in t_fly:
            t_price = self.history_sell.get_t_price(index)
            t_num = self.history_sell.get_t_num(index)
            if t_price * (1.0 - t_gap) > low:
                print('{} T 飞的回来了, T飞价格是{}, 最低价是{}'.format(date, t_price, low))
                self.history_sell.t_re_in(index, date)
                re_in_profit += (t_price * t_gap * t_num * 100)
                re_in_profit -= (t_price * t_num * 0.1)
                re_in_profit -= (t_price * t_num * 100 * 0.00025)
        return re_in_profit
    
    def in_(self, open: float, low: float, t_gap: float, date):
        in_profit = 0.0
        t_index = self.history_sell.get_no_fly()
        if t_index == -1:
            return in_profit
        t_num = self.history_sell.get_t_num(t_index)
        if open * (1.0 - t_gap) > low:
            in_profit += (open * t_gap * t_num * 100)
            in_profit -= (open * t_num * 0.1)
            in_profit -= (open * t_num * 100 * 0.00025 * 2.0)
        else:
            in_profit -= (open * t_num * 0.1)
            in_profit -= (open * t_num * 100 * 0.00025)
            self.history_sell.t_fly(t_index, open, date)
        return in_profit
    
    def in_2(self, open: float, close: float, date):
        in_profit = 0.0
        t_index = self.history_sell.get_no_fly()
        if t_index == -1:
            return in_profit
        t_num = self.history_sell.get_t_num(t_index)
        if close < open:
            in_profit += ((open -close) * t_num * 100)
            in_profit -= (open * t_num * 0.1)
            in_profit -= (open * t_num * 100 * 0.00025 * 2.0)
        else:
            in_profit -= (open * t_num * 0.1)
            in_profit -= (open * t_num * 100 * 0.00025)
            self.history_sell.t_fly(t_index, open, date)
        return in_profit
        
    def re_in_2(self, low: float, t_gap: float, date):
        re_in_profit = 0.0
        t_fly = self.history_sell.get_all_fly()
        for index in t_fly:
            t_price = self.history_sell.get_t_price(index)
            t_num = self.history_sell.get_t_num(index)
            if t_price * (1.0 - t_gap) > low:
                print('{} T 飞的回来了, T飞价格是{}, 最低价是{}'.format(date, t_price, low))
                self.history_sell.t_re_in(index, date)
                re_in_profit += (t_price * t_gap * t_num * 100)
                re_in_profit -= (t_price * t_num * 0.1)
                re_in_profit -= (t_price * t_num * 100 * 0.00025)
        return re_in_profit

    def show(self):
        self.history_sell.show_t_info()