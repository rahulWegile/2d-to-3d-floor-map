import json

log_path = r'C:\Users\Mehak\.gemini\antigravity-cli\brain\a05fe688-4728-477d-a48b-6513acb53697\.system_generated\logs\transcript_full.jsonl'
try:
    with open(log_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            content = data.get('content', '')
            if content and 'def _expand_rooms_v4' in content:
                print(f'FOUND IN LINE {i}!')
                with open('v4_backup.txt', 'a', encoding='utf-8') as out:
                    out.write(content)
                    out.write('\n\n---NEXT---\n\n')
except Exception as e:
    print(e)
print('Done scanning')
