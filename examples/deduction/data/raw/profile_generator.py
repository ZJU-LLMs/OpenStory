import json
import hashlib

def generate_encoded_id(record):
    """
    Generate a unique encoded ID (first 8 characters of MD5 Hash).
    """
    unique_str = f"{record.get('家族', '')}_{record.get('姓名', '')}_{record.get('出现回合', '')}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:8].upper()

def filter_data_latest_residence(file_path, target_round):
    """
    Filter surviving characters:
    - Field management: Only keep specified non-empty fields.
    - Residence: Only keep the latest location at or before the current round.
    - Major Node: Keep all historical events at or before the current round.
    """
    processed_data = []
    
    # --- Configuration area: Define field names to keep here ---
    # Key is the original file field name, value is the field name after output (modify value if you want to rename)
    FIELDS_TO_KEEP = {
        "姓名": "id",
    }
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                
                appear_round = record.get('出现回合', 9999)
                death_round = record.get('死亡回合', -1)
                
                # 1. Survival judgment
                is_alive = False
                if appear_round <= target_round:
                    if death_round == -1 or death_round > target_round:
                        is_alive = True
                
                if is_alive:
                    # 2. Generate encoded ID
                    enc_id = generate_encoded_id(record)
                    
                    # 3. Process 'Residence' (take only the latest)
                    residence = record.get('居住地', [])
                    if isinstance(residence, list):
                        valid_residences = [
                            item for item in residence 
                            if item.get('回合', 9999) <= target_round
                        ]
                        if valid_residences:
                            latest = max(valid_residences, key=lambda item: item.get('回合', -1))
                            record['居住地'] = [latest]
                        else:
                            record['居住地'] = []

                    # 4. Process 'Major Node' (Keep history)
                    events = record.get('重大节点', [])
                    if isinstance(events, list):
                        record['重大节点'] = [
                            e for e in events 
                            if e.get('回合', 9999) <= target_round
                        ]

                    # 5. Build final data (Core modification point)
                    # Logic: First insert ID, then iterate through whitelist, write only when original data exists and is not empty
                    new_record = {'code': enc_id}
                    
                    for orig_key, target_key in FIELDS_TO_KEEP.items():
                        value = record.get(orig_key)
                        
                        # Determine non-empty: Not None, and not empty string, empty list, empty dictionary
                        if value is not None and value != "" and value != [] and value != {}:
                            new_record[target_key] = value
                    
                    processed_data.append(new_record)
                    
            except json.JSONDecodeError:
                continue
                
    return processed_data

# --- Usage Example (Keep path exactly as provided) ---
if __name__ == "__main__":
    x = 50
    raw_path = r'C:\Users\ziyji\project\SOS\examples\deduction\data\raw\database.jsonl'
    out_path = r'C:\Users\ziyji\project\SOS\examples\deduction\data\agents\profiles.jsonl'
    
    result = filter_data_latest_residence(raw_path, x)

    with open(out_path, 'w', encoding='utf-8') as f_out:
        for char in result:
            f_out.write(json.dumps(char, ensure_ascii=False) + '\n')
            
    print(f"Processing complete. A total of {len(result)} surviving characters have been saved.")
