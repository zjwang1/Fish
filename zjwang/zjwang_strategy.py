
class Strategy(object):
    def __init__(self, average_price: float, total_num, t_num, t_gap:float):
        self.average_price = average_price
        self.total_num = total_num
        self.cost = average_price * total_num
        self.profit = average_price * total_num
        self.t_num = t_num
        self.t_gap = t_gap
        self.need_to_reinitialize = []
    
    def calc_profit(self, price):
        #print('main profit is {}'.format(price * self.t_gap * self.t_num))
        self.profit += price * self.t_gap * self.t_num * 100.0
        if self.t_num * price > 20000.0: 
            handling_fee = self.t_num * price * 0.00025 * 2.0
        else:
            handling_fee = 10.0
        self.profit -= handling_fee
        self.profit -= (self.t_num * price * 0.001)
        
    def run(self, open:float, low:float):
        if self.total_num > 0 and open * (1.0 - self.t_gap) > low:
            #print('open is {}, low is {}'.format(open, low))
            self.calc_profit(open)
        elif self.total_num > 0 and open * (1.0 - self.t_gap) < low:
            self.total_num -= self.t_num
            self.need_to_reinitialize.append(open)
        
        # 检查需要重新买入的宝贝能不能买
        new_reinitialize = []
        for item in self.need_to_reinitialize:
            if item * (1.0 - self.t_gap) > low:
                self.calc_profit(item)
                self.total_num += self.t_num
            else:
                new_reinitialize.append(item)
        self.need_to_reinitialize = new_reinitialize 
    
    def show(self):
        print('We hava earn : {}, about rate : {}'.format(self.profit - self.cost, (self.profit - self.cost) / self.cost))
        print('We have already {} num stocks'.format(self.total_num))

