import datetime
import holidays

def is_us_business_day(date):
    """
    指定された日が米国の営業日（平日かつ祝日でない）かどうかを判定します。
    """
    us_holidays = holidays.UnitedStates()
    # weekday: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    if date.weekday() >= 5:
        return False
    if date in us_holidays:
        return False
    return True

def get_latest_us_business_day(date):
    """
    指定された日以前（当日含む）で、直近の米国の営業日を返します。
    土日祝日の場合に「前営業日の終値」を参照する際などに使用します。
    """
    curr = date
    while not is_us_business_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def get_first_business_day_on_or_after(date):
    """
    指定された日以降（当日含む）で、最初の米国の営業日を返します。
    「毎月20日以降で最初の平日」といったリバランス実施日の特定に使用します。
    """
    curr = date
    while not is_us_business_day(curr):
        curr += datetime.timedelta(days=1)
    return curr