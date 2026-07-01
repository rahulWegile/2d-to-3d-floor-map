import requests
import json

url = 'http://localhost:8081/upload'
files = {'files': open(r'c:\Users\Mehak\OneDrive\Desktop\Floor to 3D\image copy 4.png', 'rb')}
r = requests.post(url, files=files)
data = r.json()
if 'floors' in data and len(data['floors']) > 0:
    rooms = data['floors'][0].get('rooms', [])
    print(f'API returned {len(rooms)} rooms')
    if len(rooms) > 0:
        print('First room keys:', list(rooms[0].keys()))
        print(json.dumps(rooms[0], indent=2))
else:
    print('No floors in response:', data)
