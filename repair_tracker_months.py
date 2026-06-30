import sys, os, json, time
sys.path.insert(0, "/root/ksushiny_terminatory/vipalina")
os.chdir("/root/ksushiny_terminatory/vipalina")
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

with open("token_vipzerocoder.json") as f:
    token_data = json.load(f)

creds = Credentials(
    token=token_data["token"], refresh_token=token_data["refresh_token"],
    token_uri=token_data["token_uri"], client_id=token_data["client_id"],
    client_secret=token_data["client_secret"], scopes=token_data["scopes"]
)
creds.refresh(Request())
gc = gspread.authorize(creds)
tracker = gc.open_by_key("12gpTHFAQj5UDMxZdi7G8fO89_T7Wp2P7Tm6wSCEjZno")
ws = tracker.sheet1

curator_months = 12
header_row = 20
goal = 7

rows = []
for m in range(1, curator_months + 1):
    r = header_row + m
    hw = "\U0001f4ca \u0421\u0434\u0430\u043d\u043d\u044b\u0435 \u0414\u0417"
    fact = (
        f"=COUNTIFS(+ hw +!F:F;TRUE;+ hw +!E:E;\">=\"&DATE(YEAR(EDATE(C4;"+ str(m-1) +"));MONTH(EDATE(C4;"+ str(m-1) +"));1);+ hw +!E:E;\"<\"&DATE(YEAR(EDATE(C4;"+ str(m) +"));MONTH(EDATE(C4;"+ str(m) +"));1))"
    )
    prog = f"=IF(C{r}=0;0;ROUND(D{r}/C{r}*100;0))&\"%\""
    stat = f"=IF(D{r}>=C{r};\"\u2705\";IF(D{r}>6;\"\U0001f19e\";IF(D{r}>3;\"\u26a0\ufe0f\";\"\u274c\")))"
    vis = f"=REPT(\"\u2588\";MIN(10;ROUND(D{r}/C{r}*10;0)))&REPT(\"\u2591\";MAX(0;10-ROUND(D{r}/C{r}*10;0)))&\" \"&TEXT(D{r}/C{r};\"0%\")"
    rows.append([f"\u041c\u0435\u0441\u044f\u0446 {m}", goal, fact, prog, stat, vis])

start = header_row + 1
end = header_row + curator_months
rng = f"B{start}:G{end}"
print(f"Writing {curator_months} months to {rng}")
ws.update(rows, rng, value_input_option="USER_ENTERED")
print("SUCCESS")
time.sleep(2)
vals = ws.get(f"B{start}:C{end}")
for i, row in enumerate(vals, start):
    print(f"  Row {i}: {row}")
