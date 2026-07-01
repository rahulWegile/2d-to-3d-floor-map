import json

log_path = r'C:\Users\Mehak\.gemini\antigravity-cli\brain\a05fe688-4728-477d-a48b-6513acb53697\.system_generated\logs\transcript_full.jsonl'
best_v4 = ''

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
        except: continue
        
        if data.get('type') == 'PLANNER_RESPONSE' and 'tool_calls' in data:
            for tc in data['tool_calls']:
                if tc.get('name') in ['replace_file_content', 'multi_replace_file_content']:
                    args_str = tc.get('args', {})
                    if isinstance(args_str, str):
                        try: args = json.loads(args_str)
                        except: args = {}
                    else:
                        args = args_str
                    
                    if 'ReplacementContent' in args:
                        content = args['ReplacementContent']
                        if 'def _expand_rooms_v4' in content and 'def _expand_rooms_v5' in content:
                            func = 'def _expand_rooms_v4' + content.split('def _expand_rooms_v4')[1].split('def _expand_rooms_v5')[0]
                            if len(func) > len(best_v4):
                                best_v4 = func
                    
                    if 'ReplacementChunks' in args:
                        chunks = args['ReplacementChunks']
                        if isinstance(chunks, str):
                            try: chunks = json.loads(chunks)
                            except: chunks = []
                        for chunk in chunks:
                            content = chunk.get('ReplacementContent', '')
                            if 'def _expand_rooms_v4' in content and 'def _expand_rooms_v5' in content:
                                func = 'def _expand_rooms_v4' + content.split('def _expand_rooms_v4')[1].split('def _expand_rooms_v5')[0]
                                if len(func) > len(best_v4):
                                    best_v4 = func

print('Best V4 from tool calls length:', len(best_v4))
if best_v4:
    with open('extracted_v4_clean.py', 'w', encoding='utf-8') as out:
        out.write(best_v4)
