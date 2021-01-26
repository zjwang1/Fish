class TInfo(object):
    def __init__(self, t_price, t_num, t_date):
        self.t_price = t_price
        self.t_num = t_num
        self.t_date = t_date
        self.re_in_date = None
    def set_re_in_date(self, date):
        self.re_in_date = date
    def show(self):
        print('在{} T飞了{}手, T飞价格是{}, 在{}接回来了'.format(self.t_date, self.t_num, self.t_price, self.re_in_date))