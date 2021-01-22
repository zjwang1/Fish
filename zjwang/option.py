import argparse 
import datetime

def get_date_str(offset):
    if(offset is None):
        offset = 0
    date_str = (datetime.datetime.today() + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
    return date_str

_default = dict(
    start_date = get_date_str(-90),
    end_date = get_date_str(None),
    code = '000876.SZ',
    name = '新 希 望',
    average_price = 21.0,
    total_num = 50,
    t_num = 10,
    t_gap = 0.012
)

parser = argparse.ArgumentParser(description='One stock crawler')
parser.add_argument('--start_date', type=str, default=_default['start_date'], dest='start_date', help='Data loading start date, Default: %s' % _default['start_date'])
parser.add_argument('--end_date', type=str, default=_default['end_date'], dest='end_date', help='Data loading end date, Default: %s' % _default['end_date'])

parser.add_argument('--code', type=str, default=_default['code'], dest='code', help='Stock code, Default: %s' % _default['code'])
parser.add_argument('--name', type=str, default=_default['name'], dest='name', help='Stock name, Default: %s' % _default['name'])
parser.add_argument('--average_price', type=float, default=_default['average_price'], dest='average_price', help='Stock average_price, Default: %s' % _default['average_price'])
parser.add_argument('--total_num', type=int, default=_default['total_num'], dest='total_num', help='Stock total_num, Default: %s' % _default['total_num'])
parser.add_argument('--t_num', type=int, default=_default['t_num'], dest='t_num', help='Stock t_num, Default: %s' % _default['t_num'])
parser.add_argument('--t_gap', type=float, default=_default['t_gap'], dest='t_gap', help='Stock t_gap, Default: %s' % _default['t_gap'])
def main():
    args = parser.parse_args()
    print(args)

if __name__ == '__main__':
    main()