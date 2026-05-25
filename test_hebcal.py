import urllib.request, json
data = json.loads(urllib.request.urlopen("https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off&mod=on&nx=off&year=2026&month=x&ss=off&mf=off&c=off&geo=none&M=on&s=off&i=on").read())
valid = []
exclude = ["Erev", "CH\"M", "Chanukah", "Purim", "Tish'a", "Hoshana", "Yom HaZikaron", "Yom HaShoah", "Sigd", "Yom HaAliyah", "Herzl", "Rabin", "Family", "Tu B'", "Lag B'", "Shushan", "Tzom", "Asara", "Fast", "Ta'anit", "Chag HaBanot", "Pesach Sheni", "Leil"]
for i in data.get("items", []):
    title = i.get("title", "")
    if any(x in title for x in exclude):
        continue
    # Only keep major holidays that are Yemei Shabaton
    # Rosh Hashana, Yom Kippur, Sukkot I, Shmini Atzeret, Pesach I, Pesach VII, Shavuot, Yom HaAtzmaut
    valid.append(title)
print(len(valid))
print('\n'.join(valid))
