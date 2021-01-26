from t_info import TInfo
class HistorySell(object):
    def __init__(self, t_context, t_list = [10, 5, 5, 10]):
        self.t_list = t_list
        self.index_price = {}
        self.t_valid = {}
        for i in range(0, len(t_list)):
            self.t_valid[i] = False
        self.t_info = [TInfo(None, None, None)] * len(t_list)
        self.t_context = t_context
    
    def t_fly(self, index, sell_price: float, fly_date):
        self.t_valid[index] = True
        self.index_price[index] = sell_price
        self.t_info[index] = TInfo(sell_price, self.t_list[index], fly_date)
        #self.t_context.add_trace(self.t_info[index])
    
    def t_re_in(self, index, re_in_date):
        self.t_valid[index] = False
        self.index_price[index] = 0.0
        self.t_info[index].set_re_in_date(re_in_date)
        self.t_context.add_trace(self.t_info[index])
    
    def get_no_fly(self):
        for i in range(0, len(self.t_list)):
            if self.t_valid[i] == False:
                return i
        return -1
    
    def get_all_fly(self):
        fly = []
        for i in range(0, len(self.t_list)):
            if self.t_valid[i] == True:
                fly.append(i)
        return fly

    def get_t_num(self, index):
        return self.t_list[index]

    def get_t_price(self, index):
        return self.index_price[index]

    def show_t_info(self):
        for info in self.t_info:
            info.show()