import urllib.request, json
valid_prefixes = ("Rosh Hashana", "Yom Kippur", "Sukkot I", "Shmini Atzeret", "Pesach I", "Pesach VII", "Shavuot", "Yom HaAtzma")
count = 0
for year in (2026, 2027):
    url = f"https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off&mod=on&nx=off&year={year}&month=x&ss=off&mf=off&c=off&geo=none&M=on&s=off&i=on"
    data = json.loads(urllib.request.urlopen(url).read())
    for item in data.get("items", []):
        title = item.get("title", "")
        if "Erev" in title or "CH\"M" in title: continue
        if any(title.startswith(p) for p in valid_prefixes):
            print(f"{year}: {title}")
            count += 1
print(f"Total: {count}")
