from t_info import TInfo
class TContext(object):
    def __init__(self):
        self.t_trace = []
    def add_trace(self, t_info):
        self.t_trace.append(t_info)
    def show_trace(self):
        self.t_trace.sort(key=lambda x:x.t_date)
        for t_info in self.t_trace:
            t_info.show()