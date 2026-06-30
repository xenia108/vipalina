import gspread, sys, time
from google.oauth2.service_account import Credentials
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file('vipalina_google_service_account.json', scopes=scopes)
gc = gspread.authorize(creds)
print(f'[{time.strftime("%H:%M:%S")}] Auth OK, opening sheet...')
sh = gc.open_by_key('1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM')
ws = sh.worksheet('Общий список new')
print(f'[{time.strftime("%H:%M:%S")}] Sheet open, reading all values...')
all_data = ws.get_all_values()
print(f'[{time.strftime("%H:%M:%S")}] Got {len(all_data)} rows')
target = '498705595'
for i in range(20, len(all_data)):
    row = all_data[i]
    if len(row) > 0 and target in str(row[0]):
        print(f'FOUND col A row {i+1}: {row[:6]}')
        sys.exit(0)
    if len(row) > 1 and target in str(row[1]):
        print(f'FOUND col B row {i+1}: {row[:6]}')
        sys.exit(0)
print('NOT FOUND')
