import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.services.address_service import get_streets_for_city

afula = get_streets_for_city('עפולה')
print("Total streets:", len(afula))
for s in afula:
    if 'יסוד' in s:
        print(s)
